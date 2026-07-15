import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from pydantic import ValidationError

from app.core.config import settings
from app.llm.base import LLMProvider, LLMProviderError, LLMProviderUnavailableError
from app.llm.factory import create_llm_provider
from app.llm.prompt_types import PromptBundle
from app.llm.report_prompts import build_report_prompt, build_report_repair_prompt
from app.schemas.event import Article, EventContext, Sentiment
from app.schemas.report import EventOverview, ReportResponse
from app.services.report_features import ReportFeatures, extract_report_features


logger = logging.getLogger(__name__)


class ReportGenerationError(LLMProviderError):
    """Raised when a provider response cannot produce a valid report."""


@dataclass(frozen=True)
class GroundingDecision:
    """Internal, non-user-visible explanation for a grounded overview value."""

    value: str | None
    reason_code: str | None = None


@dataclass(frozen=True)
class EventTimeCandidate:
    year: int | None
    month: int | None
    day: int | None
    hour: int | None
    minute: int | None
    day_period: str | None
    precision: int
    news_id: int | str | None
    quote: str
    normalized_datetime: str
    display: str


@dataclass(frozen=True)
class LocationCandidate:
    normalized_name: str
    components: tuple[str, ...]
    precision: int
    news_id: int | str | None
    quote: str


@dataclass(frozen=True)
class CauseCandidate:
    cause_text: str | None
    normalized_subject: str | None
    status: str
    investigation_ongoing: bool
    evidence: tuple[tuple[int | str | None, str], ...]


class ReportService:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        top_k: int = 5,
        article_max_chars: int = 1000,
    ) -> None:
        self.provider = provider if provider is not None else create_llm_provider(
            settings.llm_provider,
            config=settings,
        )
        self.top_k = max(top_k, 1)
        self.article_max_chars = max(article_max_chars, 1)

    def generate(self, event: EventContext) -> ReportResponse:
        articles = self.select_report_articles(event.articles)
        if self.provider.name == "fake":
            return self._build_fake_report(event, articles)

        initial_prompt = build_report_prompt(event, articles, self.article_max_chars)
        raw_output = self._generate_safely(initial_prompt, articles, repair=False)
        try:
            parsed_report = self._parse_report(raw_output)
            return self._finalize_report(event, articles, parsed_report)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            self._log_report_parse_failure(
                phase="initial",
                exc=exc,
                articles=articles,
                raw_output_chars=len(raw_output),
                repair=False,
            )
            repair_prompt = build_report_repair_prompt(
                event,
                articles,
                self.article_max_chars,
                raw_output,
            )
            logger.info(
                "report_repair_started provider=%s model=%s selected_article_count=%s "
                "selected_article_content_lengths=%s system_prompt_chars=%s user_prompt_chars=%s "
                "raw_output_chars=%s repair=%s",
                self._provider_name(),
                self._provider_model(),
                len(articles),
                self._article_content_lengths(articles),
                len(repair_prompt.system_prompt),
                len(repair_prompt.user_prompt),
                len(raw_output),
                True,
            )
            repaired_output = self._generate_safely(repair_prompt, articles, repair=True)
            try:
                parsed_report = self._parse_report(repaired_output)
                return self._finalize_report(event, articles, parsed_report)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                self._log_report_parse_failure(
                    phase="repair",
                    exc=exc,
                    articles=articles,
                    raw_output_chars=len(repaired_output),
                    repair=True,
                )
                self._log_report_exception(
                    "report_generation_failed",
                    exc,
                    articles=articles,
                    repair=True,
                )
                raise ReportGenerationError("Report output validation failed") from exc

    def select_report_articles(self, articles: list[Article]) -> list[Article]:
        valid = self._deduplicate_articles(
            [article for article in articles if article.content.strip()]
        )
        if len(valid) <= self.top_k:
            return self._sort_by_publish_time(valid)

        ordered = self._sort_by_publish_time(valid)
        selected: list[Article] = []
        if ordered:
            selected.append(ordered[0])
        if len(ordered) > 1 and ordered[-1] not in selected:
            selected.append(ordered[-1])

        covered_sources = {article.source for article in selected if article.source}
        for article in ordered:
            if len(selected) >= self.top_k:
                break
            if article in selected:
                continue
            if article.source and article.source not in covered_sources:
                selected.append(article)
                covered_sources.add(article.source)

        for article in ordered:
            if len(selected) >= self.top_k:
                break
            if article not in selected:
                selected.append(article)
        return self._sort_by_publish_time(selected)

    def _generate_safely(
        self,
        prompt: PromptBundle,
        articles: list[Article],
        *,
        repair: bool,
    ) -> str:
        started = time.perf_counter()
        try:
            response = self.provider.generate(prompt)
        except LLMProviderError as exc:
            self._log_report_exception(
                "report_provider_call_failed",
                exc,
                articles=articles,
                prompt=prompt,
                repair=repair,
                provider_call_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        except (TimeoutError, ConnectionError) as exc:
            mapped = LLMProviderUnavailableError("Report provider is unavailable")
            mapped.diagnostic_category = (
                "provider_timeout" if isinstance(exc, TimeoutError) else "provider_connection"
            )
            self._log_report_exception(
                "report_provider_call_failed",
                mapped,
                articles=articles,
                prompt=prompt,
                repair=repair,
                provider_call_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise mapped from exc
        except Exception as exc:
            mapped = ReportGenerationError("Report provider failed")
            mapped.diagnostic_category = "provider_unexpected_error"
            self._log_report_exception(
                "report_provider_call_failed",
                mapped,
                articles=articles,
                prompt=prompt,
                repair=repair,
                provider_call_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise mapped from exc
        if not isinstance(response, str) or not response.strip():
            exc = ReportGenerationError("Report provider returned an empty response")
            exc.diagnostic_category = "provider_empty_response"
            self._log_report_exception(
                "report_provider_call_failed",
                exc,
                articles=articles,
                prompt=prompt,
                repair=repair,
                provider_call_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise exc
        response = response.strip()
        metadata = self._provider_response_metadata()
        logger.info(
            "report_provider_call_succeeded provider=%s model=%s selected_article_count=%s "
            "selected_article_content_lengths=%s system_prompt_chars=%s user_prompt_chars=%s "
            "provider_call_ms=%s raw_output_chars=%s repair=%s finish_reason=%s token_usage=%s",
            self._provider_name(),
            self._provider_model(),
            len(articles),
            self._article_content_lengths(articles),
            len(prompt.system_prompt),
            len(prompt.user_prompt),
            round((time.perf_counter() - started) * 1000, 2),
            len(response),
            repair,
            metadata.get("finish_reason"),
            metadata.get("token_usage"),
        )
        return response

    def _log_report_parse_failure(
        self,
        *,
        phase: str,
        exc: Exception,
        articles: list[Article],
        raw_output_chars: int,
        repair: bool,
    ) -> None:
        base = {
            "provider": self._provider_name(),
            "model": self._provider_model(),
            "selected_article_count": len(articles),
            "selected_article_content_lengths": self._article_content_lengths(articles),
            "raw_output_chars": raw_output_chars,
            "repair": repair,
            "phase": phase,
        }
        if isinstance(exc, json.JSONDecodeError):
            logger.warning(
                "report_json_decode_failed provider=%(provider)s model=%(model)s "
                "selected_article_count=%(selected_article_count)s "
                "selected_article_content_lengths=%(selected_article_content_lengths)s "
                "raw_output_chars=%(raw_output_chars)s repair=%(repair)s phase=%(phase)s "
                "exception_type=%(exception_type)s json_line=%(json_line)s json_column=%(json_column)s json_position=%(json_position)s",
                {
                    **base,
                    "exception_type": type(exc).__name__,
                    "json_line": exc.lineno,
                    "json_column": exc.colno,
                    "json_position": exc.pos,
                },
            )
            return
        if isinstance(exc, ValidationError):
            paths = [
                {"path": ".".join(str(part) for part in error.get("loc", ())), "type": error.get("type")}
                for error in exc.errors()
            ]
            logger.warning(
                "report_schema_validation_failed provider=%(provider)s model=%(model)s "
                "selected_article_count=%(selected_article_count)s "
                "selected_article_content_lengths=%(selected_article_content_lengths)s "
                "raw_output_chars=%(raw_output_chars)s repair=%(repair)s phase=%(phase)s "
                "exception_type=%(exception_type)s validation_errors=%(validation_errors)s",
                {**base, "exception_type": type(exc).__name__, "validation_errors": paths},
            )
            return
        self._log_report_exception(
            "report_output_processing_failed",
            exc,
            articles=articles,
            repair=repair,
            raw_output_chars=raw_output_chars,
            phase=phase,
        )

    def _log_report_exception(
        self,
        message: str,
        exc: Exception,
        *,
        articles: list[Article],
        prompt: PromptBundle | None = None,
        repair: bool,
        raw_output_chars: int | None = None,
        phase: str | None = None,
        provider_call_ms: float | None = None,
    ) -> None:
        safe_exception = RuntimeError(type(exc).__name__)
        logger.exception(
            "%s provider=%s model=%s selected_article_count=%s "
            "selected_article_content_lengths=%s system_prompt_chars=%s user_prompt_chars=%s "
            "provider_call_ms=%s raw_output_chars=%s repair=%s phase=%s exception_type=%s "
            "diagnostic_category=%s provider_status_code=%s",
            message,
            self._provider_name(),
            self._provider_model(),
            len(articles),
            self._article_content_lengths(articles),
            len(prompt.system_prompt) if prompt is not None else None,
            len(prompt.user_prompt) if prompt is not None else None,
            provider_call_ms,
            raw_output_chars,
            repair,
            phase,
            type(exc).__name__,
            getattr(exc, "diagnostic_category", "report_processing"),
            getattr(exc, "provider_status_code", None),
            exc_info=(RuntimeError, safe_exception, exc.__traceback__),
        )

    def _provider_name(self) -> str:
        return str(getattr(self.provider, "name", "unknown"))

    def _provider_model(self) -> str | None:
        config = getattr(self.provider, "config", None)
        model = getattr(config, "deepseek_model", None)
        return str(model) if model else None

    @staticmethod
    def _article_content_lengths(articles: list[Article]) -> list[int]:
        return [len(article.content) for article in articles]

    def _provider_response_metadata(self) -> dict[str, object]:
        metadata = getattr(self.provider, "last_response_metadata", None)
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _parse_report(raw_output: str) -> ReportResponse:
        text = raw_output.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise TypeError("Report output must be a JSON object")
        return ReportResponse.model_validate(payload)

    def _build_fake_report(
        self,
        event: EventContext,
        articles: list[Article],
    ) -> ReportResponse:
        features = extract_report_features(event, articles)
        event_time = self._ground_event_time(None, articles).value
        location = self._ground_location(None, articles).value
        cause = self._ground_cause(None, articles).value
        persons = self._natural_person_values(articles)
        time_conflict = self._has_time_conflict(articles)
        contents = self._usable_contents(articles)
        conflict = self._has_explicit_conflict(contents)

        overview_summary = self._overview_summary(event, articles)
        summary = overview_summary
        if conflict:
            summary += " 当前报道存在冲突，报告保留不同文章的说法，不对冲突作事实裁决。"

        limitations = []
        if event_time is None:
            limitations.append(
                "当前缺少可从文章正文确认的事件发生时间。"
                if not time_conflict
                else "不同材料对事件发生时间的表述存在冲突。"
            )
        if location is None:
            limitations.append("当前材料未提供可确认的事件地点。")
        if not articles:
            limitations.append("当前没有包含正文的文章可用于报告分析。")
        if len(features.heat_history) < 2:
            limitations.append("当前缺少历史热度时间序列，无法判断真实舆情升温或降温。")
        if conflict:
            limitations.append("现有报道存在相互冲突的说法，需要进一步核验。")

        report = ReportResponse(
            overview=EventOverview(
                time=event_time,
                location=location,
                cause=cause,
                persons=persons,
                summary=overview_summary,
            ),
            summary=summary,
            trend_analysis=self._trend_analysis(event, articles),
            risk_analysis=self._risk_analysis(event, articles),
            suggestions=[
                "持续跟踪调查进展及可信来源信息。",
                "关注救援和后续处置进展。",
                "核验不同来源之间的争议信息。",
                "监测负面情绪变化，必要时准备准确回应口径。",
            ],
            limitations=limitations,
        )
        return self._finalize_report(event, articles, report)

    def _finalize_report(
        self,
        event: EventContext,
        articles: list[Article],
        parsed_report: ReportResponse,
    ) -> ReportResponse:
        contents = self._usable_contents(articles)
        features = extract_report_features(event, articles)
        limitations = []
        overview = parsed_report.overview
        relevant_aspects = set(features.relevant_fact_aspects)

        time_decision = self._ground_event_time(overview.time, articles)
        event_time = time_decision.value
        if event_time is None and "time" in relevant_aspects:
            limitations.append(
                "不同材料对事件发生时间的表述存在冲突。"
                if self._has_time_conflict(articles)
                else "当前缺少可从文章正文确认的事件发生时间。"
            )

        location_decision = self._ground_location(overview.location, articles)
        location = location_decision.value
        if location is None and "location" in relevant_aspects:
            limitations.append("当前材料未提供可确认的事件地点。")

        persons = self._ground_persons(overview.persons, articles)
        cause_decision = self._ground_cause(overview.cause, articles)
        cause = cause_decision.value

        limitations = self._report_limitations(
            features,
            event_time=event_time,
            location=location,
            cause=cause,
        ) + limitations

        payload = parsed_report.model_dump()
        payload["overview"] = {
            "time": self._sanitize_user_text(event_time) if event_time else None,
            "location": self._sanitize_user_text(location) if location else None,
            "cause": self._sanitize_user_text(cause) if cause else None,
            "persons": self._stable_unique(
                [self._sanitize_user_text(person) for person in persons]
            ),
            "summary": self._sanitize_user_text(overview.summary),
        }
        payload["summary"] = self._sanitize_user_text(parsed_report.summary)
        if self.provider.name == "fake":
            payload["trend_analysis"] = self._sanitize_user_text(
                self._trend_analysis(event, articles)
            )
            payload["risk_analysis"] = self._sanitize_user_text(
                self._risk_analysis(event, articles)
            )
            payload["suggestions"] = self._deterministic_suggestions(features)
            payload["limitations"] = self._finalize_limitations(limitations)
        else:
            payload["trend_analysis"] = self._finalize_model_trend(
                parsed_report.trend_analysis,
                features,
                event,
                articles,
            )
            payload["risk_analysis"] = self._finalize_model_risk(
                parsed_report.risk_analysis,
                features,
            )
            payload["suggestions"] = self._finalize_suggestions(
                parsed_report.suggestions,
                features,
            )
            payload["limitations"] = self._finalize_limitations(
                parsed_report.limitations + limitations,
                features,
            )
        payload = self._sanitize_report_natural_language(payload)
        return ReportResponse.model_validate(payload)

    @classmethod
    def _finalize_model_trend(
        cls,
        value: str,
        features: ReportFeatures,
        event: EventContext,
        articles: list[Article],
    ) -> str:
        text = cls._filter_irrelevant_report_text(value, features)
        if len(features.heat_history) < 2:
            safe_parts = []
            for part in re.split(r"(?<=[。！？；])", text):
                normalized = part.strip()
                if not normalized:
                    continue
                claims_trend = any(
                    marker in normalized
                    for marker in ("升温", "降温", "热度上升", "热度下降", "传播路径")
                )
                states_uncertainty = any(
                    marker in normalized
                    for marker in ("无法", "不能", "不足", "缺少", "不等同", "不代表")
                )
                if claims_trend and not states_uncertainty:
                    continue
                safe_parts.append(normalized)
            text = "".join(safe_parts)
            if text and not any(
                marker in text
                for marker in ("无法判断", "不能判断", "缺少历史热度", "没有连续热度")
            ):
                text += "当前没有连续热度数据，不能据此判断舆情升降。"
        return text or cls._trend_analysis(event, articles)

    @classmethod
    def _finalize_model_risk(
        cls,
        value: str,
        features: ReportFeatures,
    ) -> str:
        text = cls._filter_irrelevant_report_text(value, features)
        risk_level = cls._safe_snippet(features.risk_level or "")
        if not risk_level:
            return text or "上游分析结果未提供风险等级。"

        level_pattern = re.compile(
            r"(?:上游分析结果显示当前|模型判断当前|模型判断|当前)?风险等级(?:为|是)"
            r"[“\"']?(?:低|中|高)[”\"']?"
        )
        correct_statement = f"上游分析结果显示当前风险等级为“{risk_level}”"
        if level_pattern.search(text):
            text = level_pattern.sub(correct_statement, text)
        elif correct_statement not in text:
            text = correct_statement + "。" + text
        return text

    @staticmethod
    def _overview_summary(event: EventContext, articles: list[Article]) -> str:
        evidence = []
        for article in articles:
            snippet = ReportService._safe_snippet(article.content)
            if not snippet:
                continue
            identity = (
                ReportService._safe_snippet(article.source)
                or ReportService._safe_snippet(article.title)
                or "相关报道"
            )
            evidence.append(f"{identity}的文章提到：{snippet[:180]}")
        if evidence:
            return "；".join(evidence)
        safe_summary = ReportService._safe_snippet(event.summary)
        if safe_summary:
            return f"当前仅有事件背景摘要：{safe_summary}"
        safe_title = ReportService._safe_snippet(event.title)
        if safe_title:
            return f"当前仅有事件标题“{safe_title}”，其他事实信息不足。"
        return "当前信息不足，无法形成事件概述。"

    @staticmethod
    def _trend_analysis(event: EventContext, articles: list[Article]) -> str:
        features = extract_report_features(event, articles)
        parts = []
        if len(features.heat_history) >= 2:
            parts.append(ReportService._history_trend_text(features))
        else:
            parts.append(ReportService._reporting_activity_text(features))

        evolution = ReportService._content_evolution_text(features)
        if evolution:
            parts.append(evolution)
        if features.critical_information_gaps:
            parts.append(
                "当前仍需补充的信息包括"
                + "、".join(features.critical_information_gaps)
                + "。"
            )
        if len(features.heat_history) < 2:
            parts.append("由于缺少历史热度序列，无法判断整体舆情升降。")
        return "".join(parts)

    @staticmethod
    def _risk_analysis(event: EventContext, articles: list[Article]) -> str:
        features = extract_report_features(event, articles)
        risk_level = ReportService._safe_snippet(features.risk_level or "")
        conclusion = (
            f"上游分析结果显示当前风险等级为“{risk_level}”。"
            if risk_level
            else "上游分析结果未提供风险等级。"
        )

        drivers = []
        if features.heat is not None:
            drivers.append(f"当前热度为{features.heat:g}")
        safe_stage = ReportService._safe_snippet(features.stage or "")
        if safe_stage:
            drivers.append(f"事件阶段为{safe_stage}")
        if features.negative_ratio is not None:
            drivers.append(
                f"负面情绪占比为{ReportService._format_ratio(features.negative_ratio)}"
            )
        elif features.dominant_sentiment:
            drivers.append(f"主导情绪为{features.dominant_sentiment}")
        safe_keywords = [
            keyword
            for keyword in (
                ReportService._safe_snippet(item) for item in features.keywords
            )
            if keyword
        ]
        if safe_keywords:
            drivers.append("高频议题包括" + "、".join(safe_keywords))
        if features.conflict_topics:
            drivers.append("报道存在" + "、".join(features.conflict_topics))
        driver_text = (
            "风险驱动因素方面，"
            + "，".join(drivers)
            + "；这些信息构成理解当前风险的主要背景。"
            if drivers
            else "当前缺少可用于解释风险驱动因素的结构化信息。"
        )
        gap_text = (
            "关键信息缺口包括"
            + "、".join(features.critical_information_gaps)
            + "；这些缺口可能增加未经核实说法和不同口径传播的风险。"
            if features.critical_information_gaps
            else "现有材料未识别出明确的信息缺口。"
        )
        monitoring = ReportService._monitoring_focus(features)
        monitor_text = "后续监测重点包括" + "、".join(monitoring) + "。"
        return conclusion + driver_text + gap_text + monitor_text

    @staticmethod
    def _history_trend_text(features: ReportFeatures) -> str:
        values = [heat for _, heat in features.heat_history]
        first = values[0]
        last = values[-1]
        delta = last - first
        if delta > 0:
            direction = f"从{first:g}上升至{last:g}，变化幅度为{delta:g}"
        elif delta < 0:
            direction = f"从{first:g}下降至{last:g}，变化幅度为{abs(delta):g}"
        else:
            direction = f"起点和终点均为{first:g}，整体持平"

        signs = []
        for left, right in zip(values, values[1:]):
            change = right - left
            if change:
                signs.append(1 if change > 0 else -1)
        turns = sum(left != right for left, right in zip(signs, signs[1:]))
        turn_text = f"，期间出现{turns}次方向转折" if turns else "，期间未出现方向转折"
        return f"上游历史热度序列包含{len(values)}个有效点，热度{direction}{turn_text}。"

    @staticmethod
    def _reporting_activity_text(features: ReportFeatures) -> str:
        timed_count = sum(
            update.publish_time is not None and ReportService._parse_time(update.publish_time) is not None
            for update in features.chronological_updates
        )
        if timed_count >= 2 and features.report_start_time and features.report_end_time:
            start = ReportService._display_report_time(features.report_start_time)
            start_parsed = ReportService._parse_time(features.report_start_time)
            end_parsed = ReportService._parse_time(features.report_end_time)
            end = ReportService._display_report_time(
                features.report_end_time,
                include_year=not (
                    start_parsed is not None
                    and end_parsed is not None
                    and start_parsed.year == end_parsed.year
                ),
            )
            span = features.report_span_minutes or 0
            concentration = "时间较为集中" if span <= 360 else "分布跨越较长时段"
            return (
                f"现有{timed_count}篇报道发布于{start}至{end}，时间跨度约"
                f"{ReportService._format_duration(span)}，"
                f"{concentration}，反映这一时段的报道活跃度；报道活跃度不等同于真实舆情热度。"
            )
        if timed_count == 1:
            return (
                "现有1篇报道提供了有效发布时间，只能定位单个报道时点，"
                "不能据此判断报道活跃度或真实舆情热度变化。"
            )
        return "现有报道缺少有效发布时间，暂无法分析报道时间分布。"

    @staticmethod
    def _format_duration(minutes: int) -> str:
        hours, remainder = divmod(max(minutes, 0), 60)
        if hours and remainder:
            return f"{hours}小时{remainder}分钟"
        if hours:
            return f"{hours}小时"
        return f"{remainder}分钟"

    @staticmethod
    def _content_evolution_text(features: ReportFeatures) -> str:
        updates = features.chronological_updates
        if not updates:
            return "当前缺少可用于分析内容演化的报道正文。"
        earliest_focus = list(updates[0].focus)
        if len(updates) == 1:
            return "现有报道主要关注" + "、".join(earliest_focus) + "。"

        later_focus = ReportService._stable_unique(
            [focus for update in updates[1:] for focus in update.focus]
        )
        later_has_no_final_conclusion = any(
            update.states_no_final_conclusion for update in updates[1:]
        )
        later_states_rescue_started = any(
            update.states_rescue_started for update in updates[1:]
        )
        new_focus = [focus for focus in later_focus if focus not in earliest_focus]
        if later_has_no_final_conclusion:
            new_focus = [focus for focus in new_focus if focus != "最终调查结论"]
        if later_has_no_final_conclusion and later_states_rescue_started:
            new_focus = [focus for focus in new_focus if focus != "救援进展"]
        text = "较早报道主要关注" + "、".join(earliest_focus) + "。"
        if later_has_no_final_conclusion and later_states_rescue_started:
            text += "后续报道新增了救援工作已经展开的信息，并明确当前尚无最终调查结论。"
        elif new_focus:
            text += "后续报道新增或补充了" + "、".join(new_focus) + "方面的信息。"
        else:
            text += "后续报道继续围绕" + "、".join(later_focus) + "补充信息。"
        if later_has_no_final_conclusion and not later_states_rescue_started:
            text += "后续报道明确当前尚无最终调查结论。"
        return text

    @staticmethod
    def _report_limitations(
        features: ReportFeatures,
        *,
        event_time: str | None,
        location: str | None,
        cause: str | None,
    ) -> list[str]:
        limitations = []
        missing_facts = []
        aspects = set(features.relevant_fact_aspects)
        if event_time is None and "time" in aspects:
            missing_facts.append("事件发生时间")
        if location is None and "location" in aspects:
            missing_facts.append("地点")
        if missing_facts:
            limitations.append(
                "当前材料未明确" + ReportService._join_chinese_items(missing_facts) + "。"
            )

        if features.article_count < 2 or features.source_count < 2:
            limitations.append(
                f"当前分析基于{features.article_count}篇报道、{features.source_count}个来源，"
                "报道数量和信息覆盖仍然有限。"
            )
        gaps = " ".join(features.critical_information_gaps)
        if cause and "最终调查结论" in gaps:
            limitations.append("现有材料已提供初步原因，但最终调查结论尚未正式公布。")
        elif "原因" in gaps and "最终调查结论" in gaps:
            limitations.append("现有材料显示事件原因和最终调查结论仍未明确。")
        elif "原因" in gaps:
            limitations.append("现有材料显示事件原因仍未明确。")
        elif "最终调查结论" in gaps:
            limitations.append("现有材料显示最终调查结论仍未明确。")

        missing_history = []
        if len(features.heat_history) < 2:
            missing_history.append("历史热度")
        if features.sentiment_history_count < 2:
            missing_history.append("情感时间序列")
        if missing_history:
            limitations.append(
                "当前缺少"
                + "与".join(missing_history)
                + "，无法分析相应的连续变化。"
            )
        if features.conflict_topics:
            limitations.append(
                "现有报道在"
                + "、".join(features.conflict_topics)
                + "方面存在冲突或不同表述，需要进一步核验。"
            )
        return limitations

    @staticmethod
    def _deterministic_suggestions(features: ReportFeatures) -> list[str]:
        gaps = " ".join(features.critical_information_gaps)
        suggestions = []
        if "原因" in gaps or "最终调查结论" in gaps:
            suggestions.append("持续跟踪事件调查进展及可信来源发布的后续信息。")
        if any(marker in gaps for marker in ("伤亡", "地点")):
            suggestions.append(
                "重点核验事件原因、伤亡情况等尚未明确的信息，并关注不同来源的口径差异。"
            )
        if (
            features.negative_ratio is not None
            and features.negative_ratio >= 0.5
        ):
            suggestions.append(
                "持续监测负面情绪和高频议题变化，关注可能出现的未经核实信息。"
            )
        if features.conflict_topics:
            suggestions.append(
                "关注不同来源对关键事实的表述差异，避免将单一来源说法直接作为结论。"
            )
        fallbacks = (
            "持续跟踪可信来源信息，关注事件事实的后续补充。",
            "核验尚未明确的关键信息，并关注不同来源的口径差异。",
            "监测负面情绪和高频议题变化。",
        )
        for fallback in fallbacks:
            if len(suggestions) >= 2:
                break
            if fallback not in suggestions:
                suggestions.append(fallback)
        return ReportService._semantic_unique_suggestions(suggestions)[:5]

    @staticmethod
    def _join_chinese_items(values: list[str]) -> str:
        if len(values) <= 1:
            return values[0] if values else ""
        if len(values) == 2:
            return "和".join(values)
        return "、".join(values[:-1]) + "及" + values[-1]

    @staticmethod
    def _monitoring_focus(features: ReportFeatures) -> list[str]:
        gaps = " ".join(features.critical_information_gaps)
        focus = []
        if "原因" in gaps:
            focus.append("事件原因调查进展及相关猜测")
        if "伤亡" in gaps:
            focus.append("伤亡信息口径")
        if features.conflict_topics:
            focus.append("不同来源口径是否一致")
        if features.negative_ratio is not None:
            focus.append("负面情绪变化")
        if any(ReportService._safe_snippet(item) for item in features.keywords):
            focus.append("高频议题变化")
        if "最终调查结论" in gaps:
            focus.append("最终调查结论的后续补充")
        return focus or ["事件信息的后续补充与来源一致性"]

    @staticmethod
    def _format_ratio(value: float) -> str:
        display = value * 100 if 0 <= value <= 1 else value
        return f"{display:g}%"

    @staticmethod
    def _display_report_time(value: str, *, include_year: bool = True) -> str:
        parsed = ReportService._parse_time(value)
        if parsed is None:
            return value
        prefix = f"{parsed.year}年" if include_year else ""
        return f"{prefix}{parsed.month}月{parsed.day}日{parsed.hour:02d}:{parsed.minute:02d}"

    @staticmethod
    def _sentiment_text(sentiment: Sentiment | None) -> str:
        if sentiment is None:
            return ""
        values = []
        for label, value in (
            ("正面", sentiment.positive),
            ("中性", sentiment.neutral),
            ("负面", sentiment.negative),
        ):
            if value is not None:
                display = f"{value * 100:.1f}%" if 0 <= value <= 1 else f"{value:g}"
                values.append(f"{label}{display}")
        return "情感分布为" + "、".join(values) if values else ""

    @staticmethod
    def _event_time_candidates(articles: list[Article]) -> list[EventTimeCandidate]:
        candidates: list[EventTimeCandidate] = []
        pattern = re.compile(
            r"(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
            r"\s*(?P<period>凌晨|早晨|上午|中午|下午|傍晚|晚上)?\s*"
            r"(?P<hour>\d{1,2})(?:时|点)(?:(?P<minute>\d{1,2})分?)?"
        )
        for article in articles:
            content = ReportService._safe_snippet(article.content)
            if not content:
                continue
            for sentence in re.split(r"(?<=[。！？；])", content):
                for match in pattern.finditer(sentence):
                    clause_start = max(sentence.rfind("，", 0, match.start()), sentence.rfind(",", 0, match.start())) + 1
                    clause_end_candidates = [position for position in (sentence.find("，", match.end()), sentence.find(",", match.end())) if position >= 0]
                    clause_end = min(clause_end_candidates) if clause_end_candidates else len(sentence)
                    clause = sentence[clause_start:clause_end]
                    event_markers = (
                        "发生", "事发", "出现", "报警", "停运", "事故", "开庭",
                        "宣判", "发布", "签约", "开幕", "闭幕", "开赛", "结束",
                    )
                    is_leading_event_time = not sentence[:match.start()].strip(" ，,") and any(
                        marker in sentence[match.end():] for marker in event_markers
                    )
                    if not is_leading_event_time and not any(marker in clause for marker in event_markers):
                        continue
                    candidate = ReportService._make_time_candidate(
                        match.group(0),
                        article.news_id,
                        sentence.strip(),
                    )
                    if candidate is not None:
                        candidates.append(candidate)
        return ReportService._stable_candidate_unique(candidates, lambda item: (item.normalized_datetime, item.news_id))

    @staticmethod
    def _make_time_candidate(
        value: str,
        news_id: int | str | None,
        quote: str,
    ) -> EventTimeCandidate | None:
        components = ReportService._time_components(value)
        if components is None:
            return None
        year, month, day, hour, minute, period = components
        precision = sum(part is not None for part in (year, month, day, hour, minute))
        normalized = "-".join(
            "" if part is None else f"{part:02d}"
            for part in (year, month, day, hour, minute)
        )
        return EventTimeCandidate(
            year=year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            day_period=period,
            precision=precision,
            news_id=news_id,
            quote=quote,
            normalized_datetime=normalized,
            display=value.strip(),
        )

    @staticmethod
    def _time_components(value: str) -> tuple[int | None, int | None, int | None, int | None, int | None, str | None] | None:
        text = value.strip()
        iso = re.search(r"(?:(?P<year>\d{4})-)?(?P<month>\d{1,2})-(?P<day>\d{1,2})\s+(?P<hour>\d{1,2}):(?P<minute>\d{1,2})", text)
        chinese = re.search(
            r"(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
            r"\s*(?P<period>凌晨|早晨|上午|中午|下午|傍晚|晚上)?\s*"
            r"(?P<hour>\d{1,2})(?:时|点)(?:(?P<minute>\d{1,2})分?)?",
            text,
        )
        match = iso or chinese
        if match is None:
            return None
        values = match.groupdict()
        try:
            year = int(values["year"]) if values.get("year") else None
            month = int(values["month"])
            day = int(values["day"])
            hour = int(values["hour"])
            minute = int(values["minute"]) if values.get("minute") else 0
        except (TypeError, ValueError):
            return None
        if not 1 <= month <= 12 or not 1 <= day <= 31 or not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None
        period = values.get("period")
        hour = ReportService._normalize_day_period_hour(hour, period)
        if hour is None:
            return None
        return year, month, day, hour, minute, period

    @staticmethod
    def _normalize_day_period_hour(hour: int, period: str | None) -> int | None:
        if hour < 0 or hour > 23:
            return None
        if period in {"下午", "傍晚", "晚上"} and 1 <= hour <= 11:
            return hour + 12
        if period == "中午" and 1 <= hour <= 11:
            return hour + 12
        if period in {"凌晨", "早晨", "上午"} and hour == 12:
            return 0
        return hour

    @classmethod
    def _ground_event_time(
        cls,
        model_value: str | None,
        articles: list[Article],
    ) -> GroundingDecision:
        candidates = cls._event_time_candidates(articles)
        if not candidates:
            return GroundingDecision(None, "time_no_candidate")
        if model_value is None:
            candidate = max(candidates, key=lambda item: (item.precision, -len(item.display)))
            return GroundingDecision(candidate.display)
        model_components = cls._time_components(model_value)
        if model_components is None:
            return GroundingDecision(None, "time_normalization_mismatch")
        compatible = [
            candidate
            for candidate in candidates
            if cls._time_components_compatible(model_components, (
                candidate.year, candidate.month, candidate.day, candidate.hour,
                candidate.minute, candidate.day_period,
            ))
        ]
        if not compatible:
            return GroundingDecision(None, "time_normalization_mismatch")
        candidate = max(compatible, key=lambda item: (item.precision, -len(item.display)))
        return GroundingDecision(candidate.display)

    @staticmethod
    def _time_components_compatible(
        left: tuple[int | None, int | None, int | None, int | None, int | None, str | None],
        right: tuple[int | None, int | None, int | None, int | None, int | None, str | None],
    ) -> bool:
        comparable = False
        for first, second in zip(left[:5], right[:5]):
            if first is not None and second is not None:
                comparable = True
                if first != second:
                    return False
        return comparable

    @classmethod
    def _has_time_conflict(cls, articles: list[Article]) -> bool:
        return len({candidate.normalized_datetime for candidate in cls._event_time_candidates(articles)}) > 1

    @staticmethod
    def _location_candidates(articles: list[Article]) -> list[LocationCandidate]:
        candidates: list[LocationCandidate] = []
        triggers = r"(?:事发于|发生在|位于|发生地点为|事故地点为|事发地点为|事故地点是|事发地是|地点位于)"
        pattern = re.compile(
            triggers + r"\s*(?P<place>[\u4e00-\u9fff]{2,48}?)(?=内的|内|的|出现|发生|，|。|；|$)"
        )
        for article in articles:
            content = ReportService._safe_snippet(article.content)
            if not content:
                continue
            for match in pattern.finditer(content):
                place = ReportService._normalize_location(match.group("place"))
                if not place:
                    continue
                sentence = ReportService._sentence_for_index(content, match.start(), match.end())
                components = ReportService._location_components(place)
                candidates.append(
                    LocationCandidate(
                        normalized_name=place,
                        components=components,
                        precision=max(len(components), 1),
                        news_id=article.news_id,
                        quote=sentence,
                    )
                )
        return ReportService._stable_candidate_unique(candidates, lambda item: (item.normalized_name, item.news_id))

    @staticmethod
    def _normalize_location(value: str) -> str:
        return re.sub(r"[\s，。；、]+", "", value).strip("位于在的")

    @staticmethod
    def _location_components(value: str) -> tuple[str, ...]:
        suffixes = ("产业园", "园区", "新区", "街道", "电站", "机场", "车站", "医院", "学校", "省", "市", "区", "县", "镇", "村", "路")
        components = []
        for suffix in suffixes:
            for match in re.finditer(rf"[\u4e00-\u9fff]{{1,20}}{suffix}", value):
                component = match.group(0)
                if component not in components:
                    components.append(component)
        return tuple(components)

    @classmethod
    def _ground_location(
        cls,
        model_value: str | None,
        articles: list[Article],
    ) -> GroundingDecision:
        candidates = cls._location_candidates(articles)
        if not candidates:
            return GroundingDecision(None, "location_hierarchy_mismatch")
        if model_value is None:
            candidate = max(candidates, key=lambda item: (item.precision, len(item.normalized_name)))
            return GroundingDecision(candidate.normalized_name)
        model_name = cls._normalize_location(model_value)
        compatible = [
            candidate for candidate in candidates
            if model_name in candidate.normalized_name or candidate.normalized_name in model_name
        ]
        if not compatible:
            return GroundingDecision(None, "location_hierarchy_mismatch")
        candidate = max(compatible, key=lambda item: (item.precision, len(item.normalized_name)))
        return GroundingDecision(candidate.normalized_name)

    @classmethod
    def _cause_candidates(cls, articles: list[Article]) -> list[CauseCandidate]:
        candidates: list[CauseCandidate] = []
        investigation_markers = ("具体原因仍在进一步调查", "具体原因仍在调查", "原因仍在调查", "原因正在调查", "原因尚在调查", "事故原因尚未公布")
        patterns = (
            r"初步排查显示(?P<subject>[^，。；]{2,80}?(?:故障|失效))",
            r"(?P<subject>[\u4e00-\u9fffA-Za-z0-9]+(?:故障|失效))是本次[^。；]{0,30}?初步原因",
            r"(?:异常|事故)[^。；]{0,16}?与(?P<subject>[^，。；]{2,80}?(?:故障|失效))有关",
        )
        for article in articles:
            content = cls._safe_snippet(article.content)
            if not content:
                continue
            for sentence in re.split(r"(?<=[。！？；])", content):
                sentence = sentence.strip()
                if not sentence:
                    continue
                if any(marker in sentence for marker in investigation_markers):
                    candidates.append(CauseCandidate(None, None, "under_investigation", True, ((article.news_id, sentence),)))
                for pattern in patterns:
                    match = re.search(pattern, sentence)
                    if match is None:
                        continue
                    subject = match.group("subject").strip("，。； ")
                    candidates.append(
                        CauseCandidate(
                            cause_text=subject,
                            normalized_subject=cls._normalize_cause_subject(subject),
                            status="preliminary",
                            investigation_ongoing=False,
                            evidence=((article.news_id, sentence),),
                        )
                    )
        return candidates

    @staticmethod
    def _normalize_cause_subject(value: str) -> str:
        return re.sub(r"[\s，。；、]", "", value).replace("失效", "故障")

    @classmethod
    def _ground_cause(
        cls,
        model_value: str | None,
        articles: list[Article],
    ) -> GroundingDecision:
        candidates = cls._cause_candidates(articles)
        preliminary = [candidate for candidate in candidates if candidate.cause_text]
        investigation = any(candidate.investigation_ongoing for candidate in candidates)
        if not preliminary and not investigation:
            return GroundingDecision(None, "cause_slot_not_grounded")
        model_text = cls._normalize_cause_subject(model_value or "")
        if model_value and preliminary and not any(
            candidate.normalized_subject and candidate.normalized_subject in model_text
            for candidate in preliminary
        ) and "调查" not in model_text:
            return GroundingDecision(None, "cause_slot_not_grounded")
        if preliminary:
            chosen = preliminary[0]
            if investigation:
                return GroundingDecision(f"初步原因指向{chosen.cause_text}，具体原因仍在进一步调查。")
            return GroundingDecision(f"初步原因指向{chosen.cause_text}。")
        return GroundingDecision("具体原因仍在进一步调查。")

    @classmethod
    def _natural_person_values(cls, articles: list[Article]) -> list[str]:
        values = []
        patterns = (
            r"(?:负责人|记者|发言人|驾驶员|组织者)\s*(?P<name>[赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程邢裴陆荣翁荀羊於惠甄曲封储靳段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎慕连茹习宦艾鱼容向古易慎戈廖庾终居衡步都耿满匡国文寇广禄阙东欧殳沃利蔚越隆师巩聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公][\u4e00-\u9fff]{1,3})(?=组织|表示|介绍|称|带领|负责|[，。；])",
            r"(?P<name>[赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程邢裴陆荣翁荀羊於惠甄曲封储靳段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎慕连茹习宦艾鱼容向古易慎戈廖庾终居衡步都耿满匡国文寇广禄阙东欧殳沃利蔚越隆师巩聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公][\u4e00-\u9fff]{1,3})(?:组织|带领|表示|介绍|称)",
            r"(?:队长|主帅|教练|球员|名宿|父亲|母亲|生父|生母|女友|被告|嫌疑人)"
            r"\s*(?P<name>[\u4e00-\u9fff·]{2,15}?)"
            r"(?=赛后|回应|表示|坦言|认为|称|指出|质疑|怒喷|因|疑|[，。；：“])",
        )
        for article in articles:
            content = cls._safe_snippet(article.content)
            if not content:
                continue
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    name = match.group("name")
                    if cls._is_natural_person(name) and name not in values:
                        values.append(name)
        return values

    @classmethod
    def _ground_persons(cls, values: list[str], articles: list[Article]) -> list[str]:
        supported = cls._natural_person_values(articles)
        contents = cls._usable_contents(articles)
        grounded_model_values = [
            value.strip()
            for value in values
            if cls._is_natural_person(value.strip())
            and any(value.strip() in content for content in contents)
        ]
        return cls._stable_unique(grounded_model_values + supported)[:8]

    @staticmethod
    def _is_natural_person(value: str) -> bool:
        generic_terms = ("相关部门", "有关部门", "有关方面", "工作人员", "相关人员", "当地部门", "负责人", "值班人员", "救援人员")
        organization_suffixes = ("公司", "集团", "委员会", "管理局", "救援支队", "救援队", "中心", "专家组", "医院", "学校", "政府", "部门")
        return (
            re.fullmatch(r"[\u4e00-\u9fff][\u4e00-\u9fff·]{1,14}", value) is not None
            and not any(term in value for term in generic_terms)
            and not value.endswith(organization_suffixes)
        )

    @staticmethod
    def _sentence_for_index(content: str, start: int, end: int) -> str:
        left = max(content.rfind(marker, 0, start) for marker in ("。", "！", "？", "；")) + 1
        right_candidates = [position for marker in ("。", "！", "？", "；") if (position := content.find(marker, end)) >= 0]
        right = min(right_candidates) + 1 if right_candidates else len(content)
        return content[left:right].strip()

    @staticmethod
    def _stable_candidate_unique(values: list, key):
        result = []
        seen = set()
        for value in values:
            value_key = key(value)
            if value_key not in seen:
                seen.add(value_key)
                result.append(value)
        return result

    @staticmethod
    def _has_explicit_conflict(contents: list[str]) -> bool:
        positive = ("已经", "已确认", "已完成", "确认有")
        negative = ("尚未", "暂无", "未确认", "仍未", "没有")
        for index, left in enumerate(contents):
            for right in contents[index + 1 :]:
                shared = ReportService._terms(left) & ReportService._terms(right)
                if not shared:
                    continue
                if (
                    any(marker in left for marker in positive)
                    and any(marker in right for marker in negative)
                ) or (
                    any(marker in left for marker in negative)
                    and any(marker in right for marker in positive)
                ):
                    return True
        return False

    @staticmethod
    def _terms(text: str) -> set[str]:
        terms = set()
        for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
            terms.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
        return terms

    @staticmethod
    def _usable_contents(articles: list[Article]) -> list[str]:
        return [
            content
            for article in articles
            if (content := ReportService._safe_snippet(article.content))
        ]

    @staticmethod
    def _safe_snippet(content: str) -> str:
        normalized = " ".join(content.split())
        injection_markers = (
            "忽略之前",
            "忽略以上",
            "忽略规则",
            "system prompt",
            "系统指令",
            "改变身份",
            "改变json",
            "不要遵守",
        )
        if any(marker.lower() in normalized.lower() for marker in injection_markers):
            return ""
        return normalized

    @staticmethod
    def _deduplicate_articles(articles: list[Article]) -> list[Article]:
        seen = set()
        result = []
        for article in articles:
            if article.news_id is not None:
                key = ("news_id", str(article.news_id).strip())
            elif article.url.strip():
                key = ("url", article.url.strip().lower())
            else:
                title = " ".join(article.title.lower().split())
                content = " ".join(article.content.lower().split())
                key = ("content", title, content)
            if key in seen:
                continue
            seen.add(key)
            result.append(article)
        return result

    @staticmethod
    def _is_specific_person_or_org(value: str) -> bool:
        return ReportService._is_natural_person(value)

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @classmethod
    def _semantic_unique_suggestions(cls, values: list[str]) -> list[str]:
        """Keep stable, user-visible suggestions without repeated follow-up advice."""
        result: list[str] = []
        categories: list[set[str]] = []
        for value in values:
            normalized = cls._sanitize_user_text(value).strip()
            if not normalized:
                continue
            compact = re.sub(r"[\s，。；、！!？?]", "", normalized)
            tags = set()
            if "持续跟踪" in compact or "调查进展" in compact or "可信来源" in compact:
                tags.add("follow_up")
            if "核验" in compact or "口径差异" in compact:
                tags.add("verification")
            if "负面情绪" in compact or "高频议题" in compact:
                tags.add("sentiment")
            duplicate_index = next(
                (
                    index
                    for index, (existing, existing_tags) in enumerate(zip(result, categories))
                    if compact == re.sub(r"[\s，。；、！!？?]", "", existing)
                    or (tags == {"follow_up"} and existing_tags == {"follow_up"})
                ),
                None,
            )
            if duplicate_index is None:
                result.append(normalized)
                categories.append(tags)
            elif len(normalized) > len(result[duplicate_index]):
                result[duplicate_index] = normalized
                categories[duplicate_index] = tags
        return result

    @staticmethod
    def _sanitize_user_text(value: str) -> str:
        text = value.strip()
        had_object_wrapper = bool(
            re.search(
                r"(?i)\b(?:EventContext|Article|EventAnalysis|Sentiment|"
                r"ReportResponse|EventOverview|dict)\s*\(",
                text,
            )
        )
        text = re.sub(
            r"(?i)\b(?:EventContext|Article|EventAnalysis|Sentiment|"
            r"ReportResponse|EventOverview|dict)\s*\(",
            "",
            text,
        )
        text = re.sub(
            r"(?i)\b(?:articles?|news)\s*\[\s*\d+\s*\]\s*\.\s*",
            "",
            text,
        )
        text = re.sub(
            r"(?i)\b(?:event|analysis|article|articles|overview)\s*\.\s*",
            "",
            text,
        )
        text = re.sub(
            r"[（(]\s*(?:(?:news|article|event)[_\s-]?id)\s*(?:[=:：#]\s*)?"
            r"(?:\[\s*)?\d+(?:\s*[,，、和及]\s*\d+)*(?:\s*\])?\s*[)）]",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(?i)(?<![A-Za-z0-9_])(?:news|article)[_\s-]?id\s*"
            r"(?:[=:：#]\s*)?(?:\[\s*)?\d+(?:\s*[,，、和及]\s*\d+)*(?:\s*\])?",
            "相关报道",
            text,
        )
        text = re.sub(
            r"(?i)(?<![A-Za-z0-9_])event[_\s-]?id\s*(?:[=:：#]\s*)?\d+",
            "当前事件",
            text,
        )
        replacements = (
            (r"(?i)(?<![A-Za-z0-9_])news_id(?![A-Za-z0-9_])", "相关报道"),
            (r"(?i)(?<![A-Za-z0-9_])article_id(?![A-Za-z0-9_])", "相关报道"),
            (r"(?i)(?<![A-Za-z0-9_])event_id(?![A-Za-z0-9_])", "当前事件"),
            (r"(?i)(?<![A-Za-z0-9_])publish_time(?![A-Za-z0-9_])", "报道时间"),
            (r"(?i)(?<![A-Za-z0-9_])update_time_context_only(?![A-Za-z0-9_])", "上下文更新时间"),
            (r"(?i)(?<![A-Za-z0-9_])update_time(?![A-Za-z0-9_])", "更新时间"),
            (r"(?i)(?<![A-Za-z0-9_])heat_history(?![A-Za-z0-9_])", "历史热度变化"),
            (r"(?i)(?<![A-Za-z0-9_])sentiment_history_count(?![A-Za-z0-9_])", "情感变化数据"),
            (r"(?i)(?<![A-Za-z0-9_])dominant_sentiment(?![A-Za-z0-9_])", "主要情感倾向"),
            (r"(?i)(?<![A-Za-z0-9_])negative_ratio(?![A-Za-z0-9_])", "负面情绪占比"),
            (r"(?i)(?<![A-Za-z0-9_])risk_level(?![A-Za-z0-9_])", "风险等级"),
            (r"(?i)(?<![A-Za-z0-9_])keywords(?![A-Za-z0-9_])", "高频议题"),
            (r"(?i)(?<![A-Za-z0-9_])sentiment(?![A-Za-z0-9_])", "情感倾向"),
            (r"(?i)(?<![A-Za-z0-9_])heat(?![A-Za-z0-9_])", "热度"),
            (r"(?i)(?<![A-Za-z0-9_])stage(?![A-Za-z0-9_])", "生命周期阶段"),
            (r"(?i)(?<![A-Za-z0-9_])article_count(?![A-Za-z0-9_])", "报道数量"),
            (r"(?i)(?<![A-Za-z0-9_])source_count(?![A-Za-z0-9_])", "来源数量"),
            (r"(?i)(?<![A-Za-z0-9_])trend_analysis(?![A-Za-z0-9_])", "趋势分析"),
            (r"(?i)(?<![A-Za-z0-9_])risk_analysis(?![A-Za-z0-9_])", "风险分析"),
            (r"(?i)(?<![A-Za-z0-9_])quoted_news_ids(?![A-Za-z0-9_])", "引用关系"),
            (r"(?i)(?<![A-Za-z0-9_])duplicate_group_id(?![A-Za-z0-9_])", "重复内容分组"),
            (r"(?i)(?<![A-Za-z0-9_])reference_urls(?![A-Za-z0-9_])", "参考链接"),
            (r"(?i)(?<![A-Za-z0-9_])overview(?![A-Za-z0-9_])", "事件概述"),
            (r"(?i)(?<![A-Za-z0-9_])summary(?![A-Za-z0-9_])", "总结"),
            (r"(?i)(?<![A-Za-z0-9_])suggestions(?![A-Za-z0-9_])", "建议"),
            (r"(?i)(?<![A-Za-z0-9_])limitations(?![A-Za-z0-9_])", "分析边界"),
            (r"(?i)(?<![A-Za-z0-9_])location(?![A-Za-z0-9_])", "地点"),
            (r"(?i)(?<![A-Za-z0-9_])cause(?![A-Za-z0-9_])", "原因"),
            (r"(?i)(?<![A-Za-z0-9_])time(?![A-Za-z0-9_])", "时间"),
            (r"(?i)(?<![A-Za-z0-9_])title(?![A-Za-z0-9_])", "标题"),
            (r"(?i)(?<![A-Za-z0-9_])source(?![A-Za-z0-9_])", "来源"),
            (r"(?i)(?<![A-Za-z0-9_])platform(?![A-Za-z0-9_])", "平台"),
            (r"(?i)(?<![A-Za-z0-9_])content(?![A-Za-z0-9_])", "正文"),
            (r"(?i)(?<![A-Za-z0-9_])url(?![A-Za-z0-9_])", "链接"),
            (r"(?i)persons字段为空", "当前材料未明确提及具体涉事人物或机构名称"),
            (r"(?i)persons字段", "涉事人物或机构信息"),
            (r"(?i)selected_articles", "现有报道"),
            (r"所选文章", "现有报道"),
            (r"(?i)top_k", "文章筛选范围"),
            (r"(?i)top-k", "文章筛选范围"),
            (r"(?i)provider", "模型服务"),
            (r"(?i)promptbundle", "分析指令"),
            (r"(?i)prompt", "分析指令"),
            (r"(?i)eventcontext", "事件上下文"),
            (r"(?i)schema", "数据结构"),
            (r"(?i)\bpersons\b", "涉事人物或机构信息"),
            (r"5号", "本报告"),
            (r"选中文章", "现有报道"),
            (r"最终调查结论尚未公布", "现有材料显示尚无最终调查结论"),
            (r"已经证实", "现有材料显示"),
            (r"已经确认", "现有材料显示"),
            (r"(?<!未)已确认", "现有材料显示"),
        )
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)
        text = re.sub(
            r"(?<![A-Za-z0-9])[_A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?![A-Za-z0-9])",
            "相关信息",
            text,
        )
        text = re.sub(
            r"[\"']?(热度|情感倾向|主要情感倾向|风险等级|生命周期阶段|高频议题|"
            r"报道时间|更新时间|上下文更新时间|报道数量|来源数量|原因|地点|时间|标题|"
            r"来源|平台|正文|链接|相关信息)[\"']?\s*[:=：]\s*",
            r"\1为",
            text,
        )
        text = re.sub(r"(?i)\b(?:None|null|nan)\b", "未提供", text)
        text = re.sub(r"(?i)\bTrue\b", "是", text)
        text = re.sub(r"(?i)\bFalse\b", "否", text)
        text = text.replace("`", "").replace("{", "").replace("}", "")
        text = text.replace("[", "").replace("]", "")
        if had_object_wrapper:
            text = re.sub(r"\)\s*(?=(?:的|，|。|；|$))", "", text)
        text = re.sub(r"[（(]\s*[)）]", "", text)
        text = re.sub(r"(?:相关报道\s*[、,，]\s*)+相关报道", "多篇相关报道", text)
        text = re.sub(r"\s+([，。；：！？])", r"\1", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    @classmethod
    def _sanitize_report_natural_language(cls, payload: dict) -> dict:
        overview = dict(payload.get("overview") or {})
        for key in ("time", "location", "cause", "summary"):
            value = overview.get(key)
            if isinstance(value, str):
                overview[key] = cls._sanitize_user_text(value)
        overview["persons"] = [
            cls._sanitize_user_text(value)
            for value in overview.get("persons", [])
            if isinstance(value, str) and cls._sanitize_user_text(value)
        ]
        payload["overview"] = overview
        for key in ("summary", "trend_analysis", "risk_analysis"):
            value = payload.get(key)
            if isinstance(value, str):
                payload[key] = cls._sanitize_user_text(value)
        for key in ("suggestions", "limitations"):
            payload[key] = [
                cls._sanitize_user_text(value)
                for value in payload.get(key, [])
                if isinstance(value, str) and cls._sanitize_user_text(value)
            ]
        return payload

    @classmethod
    def _filter_irrelevant_report_text(
        cls,
        value: str,
        features: ReportFeatures,
    ) -> str:
        text = cls._sanitize_user_text(value)
        aspects = set(features.relevant_fact_aspects)
        parts = []
        for part in re.split(r"(?<=[。！？；])", text):
            normalized = part.strip()
            if not normalized:
                continue
            if "casualty" not in aspects and any(
                marker in normalized
                for marker in ("伤亡", "伤者", "受伤", "遇难", "死亡人数")
            ):
                continue
            if "investigation" not in aspects and any(
                marker in normalized
                for marker in ("最终调查结论", "事故调查", "救援进展", "搜救进展")
            ):
                continue
            if "location" not in aspects and any(
                marker in normalized
                for marker in ("地点", "发生地", "事发地")
            ):
                continue
            if "time" not in aspects and "事件发生时间" in normalized:
                continue
            parts.append(normalized)
        return "".join(parts)

    @classmethod
    def _finalize_suggestions(
        cls,
        values: list[str],
        features: ReportFeatures | None = None,
    ) -> list[str]:
        replacements = (
            ("建议相关部门加快调查", "持续跟踪调查进展及可信来源信息。"),
            ("立即通过官方渠道发布", "必要时准备准确统一的回应材料。"),
            ("主动开展辟谣", "核验伤亡、原因等争议信息。"),
            ("持续发布", "持续跟踪调查进展及可信来源信息。"),
            ("加强现场救援", "关注救援和后续处置进展。"),
            ("加强救援", "关注救援和后续处置进展。"),
            ("开展善后", "关注救援和后续处置进展。"),
            ("立即通报", "必要时准备准确回应口径。"),
        )
        result = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            for marker, safe_text in replacements:
                if marker in normalized:
                    normalized = safe_text
                    break
            normalized = (
                cls._filter_irrelevant_report_text(normalized, features)
                if features is not None
                else cls._sanitize_user_text(normalized)
            )
            if normalized and normalized not in result:
                result.append(normalized)

        fallbacks = (
            "对比不同来源对事件核心事实和观点的表述差异。",
            "关注与当前事件核心议题直接相关的新增信息。",
            "结合后续报道观察争议焦点和公众情绪是否发生变化。",
        )
        for fallback in fallbacks:
            if len(result) >= 2:
                break
            if fallback not in result:
                result.append(fallback)
        unique = cls._semantic_unique_suggestions(result)
        for fallback in fallbacks:
            if len(unique) >= 2:
                break
            if fallback not in unique:
                unique.append(fallback)
        return unique[:5]

    @classmethod
    def _finalize_limitations(
        cls,
        values: list[str],
        features: ReportFeatures | None = None,
    ) -> list[str]:
        limitations = cls._stable_unique(
            [
                cls._filter_irrelevant_report_text(value, features)
                if features is not None
                else cls._sanitize_user_text(value)
                for value in values
            ]
        )
        result = []
        covered_categories: list[set[str]] = []
        for item in limitations:
            categories = cls._limitation_categories(item)
            if (
                categories
                and "模型给出的" not in item
                and "保守移除" not in item
                and any(categories <= covered for covered in covered_categories)
            ):
                continue
            result.append(item)
            if len(categories) >= 2 and "模型给出的" not in item:
                covered_categories.append(categories)
        return result

    @staticmethod
    def _limitation_categories(value: str) -> set[str]:
        categories = set()
        if "事件发生时间" in value:
            categories.add("time")
        if "地点" in value:
            categories.add("location")
        if any(marker in value for marker in ("涉事人物", "涉及人员", "人物、机构或组织")):
            categories.add("persons")
        if "原因" in value:
            categories.add("cause")
        if "最终调查结论" in value:
            categories.add("conclusion")
        if "历史热度" in value:
            categories.add("heat_history")
        if "情感时间序列" in value:
            categories.add("sentiment_history")
        return categories

    @staticmethod
    def _sort_by_publish_time(articles: list[Article]) -> list[Article]:
        indexed = list(enumerate(articles))

        def key(item: tuple[int, Article]) -> tuple[int, datetime, int]:
            index, article = item
            parsed = ReportService._parse_time(article.publish_time)
            return (0, parsed, index) if parsed is not None else (1, datetime.max, index)

        return [article for _, article in sorted(indexed, key=key)]

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed


@lru_cache
def get_report_service() -> ReportService:
    return ReportService(
        provider=create_llm_provider(settings.llm_provider, config=settings),
        top_k=settings.report_top_k,
        article_max_chars=settings.report_article_max_chars,
    )
