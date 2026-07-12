import json
import re
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


class ReportGenerationError(LLMProviderError):
    """Raised when a provider response cannot produce a valid report."""


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

        raw_output = self._generate_safely(
            build_report_prompt(event, articles, self.article_max_chars)
        )
        try:
            parsed_report = self._parse_report(raw_output)
            return self._finalize_report(event, articles, parsed_report)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            repaired_output = self._generate_safely(
                build_report_repair_prompt(
                    event,
                    articles,
                    self.article_max_chars,
                    raw_output,
                )
            )
            try:
                parsed_report = self._parse_report(repaired_output)
                return self._finalize_report(event, articles, parsed_report)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
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

    def _generate_safely(self, prompt: PromptBundle) -> str:
        try:
            response = self.provider.generate(prompt)
        except LLMProviderError:
            raise
        except (TimeoutError, ConnectionError) as exc:
            raise LLMProviderUnavailableError("Report provider is unavailable") from exc
        except Exception as exc:
            raise ReportGenerationError("Report provider failed") from exc
        if not isinstance(response, str) or not response.strip():
            raise ReportGenerationError("Report provider returned an empty response")
        return response.strip()

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
        contents = self._usable_contents(articles)
        features = extract_report_features(event, articles)
        event_time, time_conflict = self._extract_event_time(contents)
        location = self._extract_location(contents)
        cause = self._extract_cause(contents)
        persons = self._extract_persons(contents)
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

        supported_times = self._event_time_values(contents)
        time_conflict = len(supported_times) > 1
        event_time = overview.time if overview.time in supported_times else None
        if overview.time is not None and event_time is None:
            limitations.append("模型给出的事件发生时间缺少现有报道正文支持，已保守清除。")
        if event_time is None and not any("事件发生时间" in item for item in limitations):
            limitations.append(
                "不同材料对事件发生时间的表述存在冲突。"
                if time_conflict
                else "当前缺少可从文章正文确认的事件发生时间。"
            )

        supported_locations = self._location_values(contents)
        location = overview.location if overview.location in supported_locations else None
        if overview.location is not None and location is None:
            limitations.append("模型给出的事件地点缺少现有报道正文支持，已保守清除。")
        if location is None and not any("事件地点" in item for item in limitations):
            limitations.append("当前材料未提供可确认的事件地点。")

        persons = []
        for person in overview.persons:
            normalized = person.strip()
            if (
                normalized
                and any(normalized in content for content in contents)
                and self._is_specific_person_or_org(normalized)
                and normalized not in persons
            ):
                persons.append(normalized)
        if len(persons) < len(overview.persons):
            limitations.append("部分人物、机构或组织缺少现有报道正文支持，已保守移除。")

        cause = self._ground_cause(overview.cause, contents)
        if overview.cause is not None and cause is None:
            limitations.append("模型给出的事件原因缺少现有报道正文支持，已保守清除。")

        limitations = self._report_limitations(
            features,
            event_time=event_time,
            location=location,
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
        payload["trend_analysis"] = self._sanitize_user_text(
            self._trend_analysis(event, articles)
        )
        payload["risk_analysis"] = self._sanitize_user_text(
            self._risk_analysis(event, articles)
        )
        payload["suggestions"] = self._deterministic_suggestions(features)
        payload["limitations"] = self._finalize_limitations(limitations)
        return ReportResponse.model_validate(payload)

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
                or f"news_id={article.news_id}"
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
            end = ReportService._display_report_time(features.report_end_time)
            span = features.report_span_minutes or 0
            concentration = "时间较为集中" if span <= 360 else "分布跨越较长时段"
            return (
                f"现有{timed_count}篇报道发布在{start}至{end}之间，跨度{span}分钟，"
                f"{concentration}，反映这一时段的报道活跃度；报道活跃度不等同于真实舆情热度。"
            )
        if timed_count == 1:
            return (
                "现有1篇报道提供了有效发布时间，只能定位单个报道时点，"
                "不能据此判断报道活跃度或真实舆情热度变化。"
            )
        return "现有报道缺少有效发布时间，暂无法分析报道时间分布。"

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
    ) -> list[str]:
        limitations = []
        missing_facts = []
        if event_time is None:
            missing_facts.append("事件发生时间")
        if location is None:
            missing_facts.append("地点")
        if "具体涉事人物或机构尚未明确" in features.critical_information_gaps:
            missing_facts.append("具体涉事人物或机构名称")
        if missing_facts:
            limitations.append(
                "当前材料未明确" + ReportService._join_chinese_items(missing_facts) + "。"
            )

        limitations.append(
            f"当前分析基于{features.article_count}篇报道、{features.source_count}个来源，"
            "报道数量和信息覆盖仍然有限。"
        )
        gaps = " ".join(features.critical_information_gaps)
        if "原因" in gaps and "最终调查结论" in gaps:
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
        return ReportService._stable_unique(suggestions)[:5]

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
    def _display_report_time(value: str) -> str:
        parsed = ReportService._parse_time(value)
        return parsed.strftime("%H:%M") if parsed is not None else value

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
    def _extract_event_time(contents: list[str]) -> tuple[str | None, bool]:
        unique = ReportService._event_time_values(contents)
        return (unique[0], False) if len(unique) == 1 else (None, len(unique) > 1)

    @staticmethod
    def _event_time_values(contents: list[str]) -> list[str]:
        values = []
        patterns = (
            r"((?:\d{4}年)?\d{1,2}月\d{1,2}日(?:\s*\d{1,2}(?:时|点)(?:\d{1,2}分)?)?)"
            r"[^。；，]{0,12}(?:发生|事发)",
            r"(?:发生于|发生在|事发于)\s*"
            r"((?:\d{4}年)?\d{1,2}月\d{1,2}日(?:\s*\d{1,2}(?:时|点)(?:\d{1,2}分)?)?)",
        )
        for content in contents:
            for pattern in patterns:
                values.extend(re.findall(pattern, content))
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @staticmethod
    def _extract_location(contents: list[str]) -> str | None:
        unique = ReportService._location_values(contents)
        return unique[0] if len(unique) == 1 else None

    @staticmethod
    def _location_values(contents: list[str]) -> list[str]:
        pattern = r"(?:事发于|发生在|位于)\s*([\u4e00-\u9fff]{2,16}(?:省|市|区|县|镇|村|路|街道|机场|车站|学校|医院))"
        values = []
        for content in contents:
            values.extend(re.findall(pattern, content))
        return list(dict.fromkeys(values))

    @staticmethod
    def _ground_cause(cause: str | None, contents: list[str]) -> str | None:
        if cause is None:
            return None
        normalized = cause.strip()
        investigation_values = {"仍在调查", "原因仍在调查", "原因正在调查", "原因尚在调查"}
        if normalized in investigation_values:
            has_support = any(
                marker in content
                for content in contents
                for marker in (
                    "原因仍在调查",
                    "原因正在调查",
                    "原因尚在调查",
                    "具体原因仍在调查",
                )
            )
            return "仍在调查" if has_support else None
        return normalized if any(normalized in content for content in contents) else None

    @staticmethod
    def _extract_cause(contents: list[str]) -> str | None:
        if any(
            marker in content
            for content in contents
            for marker in ("原因仍在调查", "原因正在调查", "原因尚在调查", "具体原因仍在调查")
        ):
            return "仍在调查"
        statements = []
        for content in contents:
            statements.extend(
                match.strip()
                for match in re.findall(r"[^。！？]*(?:原因是|由于|因)[^。！？]*[。！？]?", content)
                if match.strip()
            )
        unique = list(dict.fromkeys(statements))
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            return "不同报道对事件原因的说法存在冲突"
        return None

    @staticmethod
    def _extract_persons(contents: list[str]) -> list[str]:
        pattern = r"[\u4e00-\u9fff]{2,12}(?:政府|警方|消防|医院|学校|公司|委员会|部门|救援队)"
        values = []
        for content in contents:
            values.extend(re.findall(pattern, content))
        return list(dict.fromkeys(values))

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
        generic_terms = (
            "相关部门",
            "有关部门",
            "有关方面",
            "工作人员",
            "相关人员",
            "当地部门",
        )
        if any(term in value for term in generic_terms) or value.endswith("负责人"):
            return False

        organization_suffixes = (
            "人民政府",
            "公安局",
            "应急管理局",
            "消防救援支队",
            "消防救援队",
            "医院",
            "学校",
            "公司",
            "委员会",
            "协会",
            "中心",
            "研究院",
            "集团",
        )
        if len(value) >= 4 and value.endswith(organization_suffixes):
            return True
        return re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value) is not None

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _sanitize_user_text(value: str) -> str:
        text = value.strip()
        replacements = (
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
        return text.strip()

    @classmethod
    def _finalize_suggestions(cls, values: list[str]) -> list[str]:
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
            normalized = cls._sanitize_user_text(normalized)
            if normalized and normalized not in result:
                result.append(normalized)

        fallbacks = (
            "持续跟踪调查进展及可信来源信息。",
            "核验不同来源之间的争议信息。",
            "监测负面情绪变化，必要时准备准确回应口径。",
        )
        for fallback in fallbacks:
            if len(result) >= 2:
                break
            if fallback not in result:
                result.append(fallback)
        return result[:5]

    @classmethod
    def _finalize_limitations(cls, values: list[str]) -> list[str]:
        limitations = cls._stable_unique(
            [cls._sanitize_user_text(value) for value in values]
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
