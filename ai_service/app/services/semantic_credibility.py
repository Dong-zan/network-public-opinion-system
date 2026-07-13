import json
import logging
import re
import time
from dataclasses import dataclass

from app.llm.base import LLMProvider
from app.schemas.event import Article
from app.schemas.verification import (
    ClaimSourceRoleAssessment,
    CredibilityAssessment,
    LanguageAssessment,
    SemanticCredibilityAssessment,
    SemanticLanguageRiskFlag,
    VerificationResponse,
)
from app.schemas.verification_semantic import SemanticLLMOutput


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SemanticAnalysisContext:
    target_article: Article
    verification: VerificationResponse
    source_status: str
    registered_source: bool
    domain_match: bool | None
    metadata_signals: tuple[str, ...]
    deterministic_flags: tuple[tuple[str, str], ...]
    article_max_chars: int
    articles: tuple[Article, ...]

    def to_prompt_payload(self) -> dict:
        target = self.target_article
        article_by_id = {str(article.news_id): article for article in self.articles if article.news_id is not None}
        claims = []
        for result in self.verification.claim_results:
            evidence = []
            for item in result.evidence:
                article = article_by_id.get(str(item.news_id))
                evidence.append(
                    {
                        "news_id": item.news_id,
                        "source": item.source,
                        "publish_time": article.publish_time if article else None,
                        "quote": item.quote,
                        "relation": item.stance,
                        "reason_code": item.reason_code,
                    }
                )
            for item in result.context_evidence:
                article = article_by_id.get(str(item.news_id))
                evidence.append(
                    {
                        "news_id": item.news_id,
                        "source": item.source,
                        "publish_time": article.publish_time if article else None,
                        "quote": item.quote,
                        "relation": item.relation,
                        "reason_code": item.reason_code,
                    }
                )
            claims.append(
                {
                    "claim_id": result.claim_id,
                    "claim": result.claim,
                    "verdict": result.verdict,
                    "independent_source_count": result.independent_source_count,
                    "verified_evidence": evidence,
                }
            )
        return {
            "target_article": {
                "news_id": target.news_id,
                "title": self._escape(target.title),
                "content": self._escape(target.content[: self.article_max_chars]),
                "source": self._escape(target.source),
                "platform": self._escape(target.platform),
                "is_official": target.is_official,
                "account_type": self._escape(target.account_type or ""),
                "source_type": self._escape(target.source_type or ""),
                "author": self._escape(target.author or ""),
            },
            "claims": claims,
            "metadata": {
                "source_status": self.source_status,
                "registered_source": self.registered_source,
                "domain_match": self.domain_match,
                "metadata_signals": list(self.metadata_signals),
                "deterministic_language_flags": [
                    {"type": flag_type, "quote": self._escape(quote)}
                    for flag_type, quote in self.deterministic_flags
                ],
            },
        }

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("<", "＜").replace(">", "＞")


class SemanticCredibilityValidator:
    _UNCERTAINTY_MARKERS = (
        "初步",
        "可能",
        "暂定",
        "尚未确定",
        "仍在调查",
        "待确认",
        "据初步判断",
        "截至目前",
        "尚在调查",
        "进一步调查",
    )
    _FINALITY_MARKERS = (
        "已经确定",
        "最终确定",
        "百分百确定",
        "完全确定",
        "毫无疑问",
        "不存在其他可能",
        "已查明最终原因",
        "明确证实",
        "已经证实",
    )
    _CAUSAL_MARKERS = ("导致", "因此", "正是因为", "根本原因是", "由于", "造成")

    def __init__(self, max_flags: int = 12) -> None:
        self.max_flags = max(1, max_flags)

    def validate(
        self,
        output: SemanticLLMOutput,
        context: SemanticAnalysisContext,
    ) -> tuple[list[SemanticLanguageRiskFlag], list[ClaimSourceRoleAssessment]]:
        target_texts = (context.target_article.title, context.target_article.content)
        claims = {result.claim_id: result for result in context.verification.claim_results}
        verified_evidence = {
            result.claim_id: [*result.evidence, *result.context_evidence]
            for result in context.verification.claim_results
        }
        deterministic = set(context.deterministic_flags)
        flags = []
        for flag in output.language_flags:
            if not any(flag.quote in text for text in target_texts):
                continue
            if flag.related_claim_id is not None and flag.related_claim_id not in claims:
                continue
            if not self._has_valid_evidence_reference(flag, verified_evidence):
                continue
            if not self._accept_flag(flag, claims, context, verified_evidence):
                continue
            if (flag.type, flag.quote) in deterministic:
                continue
            flags.append(flag)
        roles = []
        for role in output.source_role_assessments:
            if role.claim_id not in claims:
                continue
            if role.quote is not None and not any(role.quote in text for text in target_texts):
                continue
            normalized_role = self._normalize_role(role, context.target_article)
            if normalized_role is not None:
                roles.append(normalized_role)
        return self._stable_flags(flags)[: self.max_flags], self._stable_roles(roles)[: self.max_flags]

    @staticmethod
    def _has_valid_evidence_reference(flag, verified_evidence) -> bool:
        if flag.evidence_quote is None and flag.evidence_news_id is None:
            return True
        if flag.related_claim_id is None or flag.evidence_quote is None or flag.evidence_news_id is None:
            return False
        return any(
            item.quote == flag.evidence_quote and str(item.news_id) == str(flag.evidence_news_id)
            for item in verified_evidence[flag.related_claim_id]
        )

    def _accept_flag(self, flag, claims, context, verified_evidence) -> bool:
        if flag.type == "preliminary_as_confirmed":
            return self._is_preliminary_as_confirmed(flag, claims)
        if flag.type == "uncertainty_removed":
            return self._is_uncertainty_removed(flag, claims)
        if flag.type == "title_body_mismatch":
            return self._is_title_body_mismatch(flag, context.target_article)
        if flag.type == "unsupported_causality":
            return self._is_unsupported_causality(flag, claims, verified_evidence)
        return True

    def _is_preliminary_as_confirmed(self, flag, claims) -> bool:
        claim_text = claims[flag.related_claim_id].claim if flag.related_claim_id in claims else None
        return (
            flag.related_claim_id is not None
            and flag.evidence_quote is not None
            and self._contains_uncertainty(flag.evidence_quote)
            and self._contains_finality(flag.quote)
            and not self._contains_uncertainty(flag.quote)
            and self._same_core_subject(flag.quote, flag.evidence_quote, claim_text)
        )

    def _is_uncertainty_removed(self, flag, claims) -> bool:
        claim_text = claims[flag.related_claim_id].claim if flag.related_claim_id in claims else None
        return (
            flag.related_claim_id is not None
            and flag.evidence_quote is not None
            and self._contains_uncertainty(flag.evidence_quote)
            and not self._contains_uncertainty(flag.quote)
            and self._contains_finality_or_confirmation(flag.quote)
            and self._same_core_subject(flag.quote, flag.evidence_quote, claim_text)
        )

    def _is_title_body_mismatch(self, flag, target: Article) -> bool:
        if (
            flag.quote not in target.title
            or flag.comparison_quote is None
            or flag.comparison_quote not in target.content
        ):
            return False
        return (
            any(marker in flag.explanation for marker in ("不一致", "冲突", "相反", "矛盾", "差异"))
            and self._explicit_title_body_conflict(flag.quote, flag.comparison_quote)
        )

    def _is_unsupported_causality(self, flag, claims, verified_evidence) -> bool:
        if flag.related_claim_id is None or not self._has_specific_causal_assertion(flag.quote):
            return False
        return not any(
            self._has_specific_causal_assertion(item.quote)
            and self._same_core_subject(flag.quote, item.quote)
            for item in verified_evidence[flag.related_claim_id]
            if getattr(item, "stance", None) == "supports"
        )

    @classmethod
    def _contains_uncertainty(cls, text: str) -> bool:
        return any(marker in text for marker in cls._UNCERTAINTY_MARKERS)

    @classmethod
    def _contains_finality(cls, text: str) -> bool:
        return any(marker in text for marker in cls._FINALITY_MARKERS)

    @classmethod
    def _contains_finality_or_confirmation(cls, text: str) -> bool:
        return cls._contains_finality(text) or any(marker in text for marker in ("明确", "确认", "证实", "已查明"))

    @classmethod
    def _has_specific_causal_assertion(cls, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        if re.fullmatch(r"(?:事故|事件).{0,3}造成\d+(?:人|名).{0,4}(?:死亡|受伤|伤亡|失联)", compact):
            return False
        return any(marker in compact for marker in cls._CAUSAL_MARKERS)

    @classmethod
    def _same_core_subject(cls, first: str, second: str, claim_text: str | None = None) -> bool:
        def normalized(value: str) -> str:
            for marker in (
                *cls._UNCERTAINTY_MARKERS,
                *cls._FINALITY_MARKERS,
                "事故原因",
                "具体原因",
                "初步原因",
                "最终原因",
                "原因是",
                "排查显示",
                "已经确认",
                "明确确认",
                "指向",
                "百分百",
            ):
                value = value.replace(marker, "")
            return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", value)

        first_normalized, second_normalized = normalized(first), normalized(second)
        if not cls._has_substantial_overlap(first_normalized, second_normalized):
            return False
        if claim_text is None:
            return True
        claim_normalized = normalized(claim_text)
        return cls._has_substantial_overlap(first_normalized, claim_normalized) and cls._has_substantial_overlap(
            second_normalized, claim_normalized
        )

    @staticmethod
    def _has_substantial_overlap(first: str, second: str) -> bool:
        if len(first) < 3 or len(second) < 3:
            return False
        if min(len(first), len(second)) >= 4 and (first in second or second in first):
            return True
        first_terms = {first[index : index + 2] for index in range(len(first) - 1)}
        second_terms = {second[index : index + 2] for index in range(len(second) - 1)}
        smaller_size = min(len(first_terms), len(second_terms))
        overlap_size = len(first_terms & second_terms)
        return overlap_size >= 2 and overlap_size / smaller_size >= 0.6

    @staticmethod
    def _explicit_title_body_conflict(title_quote: str, body_quote: str) -> bool:
        pairs = (
            (("爆炸",), ("无明火", "未燃烧", "未发生燃烧", "未发生爆炸", "没有燃烧")),
            (("人员伤亡", "造成人员伤亡"), ("无人员伤亡", "未造成人员伤亡", "零伤亡")),
            (("已恢复运行", "恢复运行"), ("仍保持停运", "尚未恢复", "仍未恢复")),
            (("原因已确定", "已查明原因", "最终原因"), ("原因仍在调查", "具体原因仍在进一步调查", "尚未确定")),
        )
        return any(
            any(title_marker in title_quote for title_marker in title_markers)
            and any(body_marker in body_quote for body_marker in body_markers)
            for title_markers, body_markers in pairs
        )

    def _normalize_role(self, role: ClaimSourceRoleAssessment, target: Article) -> ClaimSourceRoleAssessment | None:
        if role.attributed_role != "unknown" and (
            role.quote is None or not self._has_attribution_cue(role.quote, role.attributed_role)
        ):
            return None
        publisher_role = role.publisher_role
        if publisher_role != "unknown" and not self._publisher_role_matches_metadata(publisher_role, target):
            publisher_role = "unknown"
        if publisher_role == "unknown" and role.attributed_role == "unknown":
            return None
        basis = (
            "attribution_quote"
            if role.attributed_role != "unknown"
            else "publisher_metadata" if publisher_role != "unknown" else "unknown"
        )
        return role.model_copy(update={"publisher_role": publisher_role, "basis": basis})

    @staticmethod
    def _publisher_role_matches_metadata(role: str, target: Article) -> bool:
        account_metadata = " ".join(
            value.lower() for value in (target.account_type or "", target.source_type or "")
        )
        media_metadata = " ".join((target.platform.lower(), account_metadata))
        markers = {
            "news_media": ("新闻", "媒体", "报", "电视", "广播"),
            "social_account": ("社交", "微博", "微信", "自媒体", "账号"),
            "operator": ("企业", "公司", "运营方"),
            "government_notice": ("政府", "政务", "党政机关", "政府部门"),
            "regulator": ("监管", "市场监管"),
            "emergency_management": ("应急管理", "应急部门"),
            "fire_rescue": ("消防救援", "消防部门"),
            "expert_group": ("专家", "研究机构"),
            "witness": ("目击", "现场"),
            "anonymous_source": ("匿名",),
        }
        metadata = media_metadata if role in {"news_media", "social_account"} else account_metadata
        return any(marker in metadata for marker in markers.get(role, ()))

    @staticmethod
    def _has_attribution_cue(quote: str, role: str) -> bool:
        cues = {
            "government_notice": ("政府", "官方", "通报", "警方", "公安", "部门"),
            "regulator": ("监管", "市场监管"),
            "emergency_management": ("应急",),
            "fire_rescue": ("消防", "救援"),
            "operator": ("公司", "企业", "运营", "厂方"),
            "expert_group": ("专家", "学者", "研究"),
            "news_media": ("媒体", "报道", "记者"),
            "witness": ("目击", "现场人员", "群众"),
            "social_account": ("网友", "社交", "微博", "自媒体"),
            "anonymous_source": ("据悉", "知情人士", "匿名"),
        }
        return any(marker in quote for marker in cues.get(role, ()))

    @staticmethod
    def _stable_flags(values: list[SemanticLanguageRiskFlag]) -> list[SemanticLanguageRiskFlag]:
        ordered = sorted(
            values,
            key=lambda item: (
                item.type,
                item.related_claim_id or 0,
                -item.severity,
                -len(item.quote),
                item.quote,
            ),
        )
        result = []
        for value in ordered:
            same_scope = [
                item
                for item in result
                if item.type == value.type and item.related_claim_id == value.related_claim_id
            ]
            if any(value.quote in item.quote or item.quote in value.quote for item in same_scope):
                continue
            result.append(value)
        return sorted(result, key=lambda item: (item.type, item.related_claim_id or 0, -item.severity, item.quote))

    @staticmethod
    def _stable_roles(values: list[ClaimSourceRoleAssessment]) -> list[ClaimSourceRoleAssessment]:
        unique = {}
        for value in values:
            unique.setdefault((value.claim_id, value.publisher_role, value.attributed_role, value.quote, value.basis), value)
        return sorted(unique.values(), key=lambda item: (item.claim_id, item.publisher_role, item.attributed_role, item.quote or ""))


class LlmSemanticCredibilityAnalyzer:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        article_max_chars: int = 5000,
        max_flags: int = 12,
    ) -> None:
        self.provider = provider
        self.article_max_chars = max(1, article_max_chars)
        self.validator = SemanticCredibilityValidator(max_flags)

    def analyze(
        self,
        target_article: Article,
        verification: VerificationResponse,
        assessment: CredibilityAssessment,
        articles: list[Article],
    ) -> SemanticCredibilityAssessment:
        context = SemanticAnalysisContext(
            target_article=target_article,
            verification=verification,
            source_status=assessment.source_assessment.status,
            registered_source=assessment.source_assessment.registered_source,
            domain_match=assessment.source_assessment.domain_match,
            metadata_signals=tuple(assessment.source_assessment.signals),
            deterministic_flags=tuple((item.type, item.quote) for item in assessment.language_assessment.flags),
            article_max_chars=self.article_max_chars,
            articles=tuple(articles),
        )
        started = time.perf_counter()
        try:
            from app.llm.verification_semantic_prompts import build_verification_semantic_prompt

            prompt = build_verification_semantic_prompt(context)
            raw = self.provider.generate(prompt)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("semantic output is empty")
            parsed = SemanticLLMOutput.model_validate(json.loads(raw.strip()))
            flags, roles = self.validator.validate(parsed, context)
            logger.info(
                "semantic_verification_completed semantic_enabled=%s provider=%s target_content_chars=%s "
                "claim_count=%s evidence_quote_count=%s call_ms=%s raw_output_chars=%s status=%s accepted_flags=%s removed_flags=%s",
                True, self.provider.name, len(target_article.content), len(verification.claim_results),
                sum(len(item.evidence) + len(item.context_evidence) for item in verification.claim_results),
                round((time.perf_counter() - started) * 1000, 2), len(raw), "success", len(flags), len(parsed.language_flags) - len(flags),
            )
            return SemanticCredibilityAssessment(status="success", analysis_method="llm", language_flags=flags, source_role_assessments=roles)
        except Exception as exc:
            logger.warning(
                "semantic_verification_fallback semantic_enabled=%s provider=%s target_content_chars=%s claim_count=%s "
                "call_ms=%s exception_type=%s status=%s",
                True, self.provider.name, len(target_article.content), len(verification.claim_results),
                round((time.perf_counter() - started) * 1000, 2), type(exc).__name__, "fallback",
            )
            return SemanticCredibilityAssessment(
                status="fallback",
                analysis_method="deterministic_fallback",
                limitations=["AI语义增强未成功，当前仅保留第一阶段确定性评估结果。"],
            )
