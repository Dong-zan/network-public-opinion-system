import json
import logging

from pydantic import ValidationError

from app.llm.base import LLMProvider
from app.llm.verification_explanation_prompts import (
    build_verification_explanation_prompt,
)
from app.schemas.event import Article, EventContext
from app.schemas.verification import ClaimVerificationResult, VerificationResponse
from app.schemas.verification_explanation import (
    ClaimAIExplanation,
    ExplainedEvidence,
    ExplanationReason,
    VerificationAIExplanation,
    VerificationExplanationLLMOutput,
    VerificationScoreBreakdown,
)
from app.services.credibility_scorer import CredibilityRiskScoringConfig
from app.services.verification_explanation_validator import (
    VerificationAIExplanationValidator,
)


logger = logging.getLogger(__name__)


class VerificationExplanationOutputFormatError(ValueError):
    """Raised when model output does not contain a usable JSON object."""


class VerificationExplanationService:
    _OUTPUT_FIELDS = {
        "headline",
        "conclusion",
        "why",
        "claim_explanations",
        "score_explanation",
        "limitations",
    }
    _AUTHENTICATION_TERMS = (
        "注册表",
        "登记",
        "尚未注册",
        "未注册",
        "域名未匹配",
        "域名匹配",
        "身份验证",
        "身份未完成验证",
    )
    _STANDARD_LIMITATIONS = (
        "本次基于当前事件内的多篇新闻进行交叉比较，重点呈现共同信息、差异和来源关系。",
    )
    _SINGLE_ARTICLE_SCOPE_LIMITATION = (
        "当前事件仅包含这篇新闻；以下内容评估来源可追溯性、文本表达和内容结构，"
        "未联网进行跨来源事实确认。"
    )
    _REPEATED_SINGLE_SOURCE_TERMS = (
        "没有其他独立新闻",
        "缺少足够独立",
        "独立来源",
        "独立证据",
        "独立证据不足",
        "独立来源数量",
        "候选文章",
        "无法确认或反驳",
        "不能确认或反驳",
        "尚不足以独立确认",
        "跨来源事实确认",
        "联网",
        "外部信息",
    )
    def __init__(
        self,
        provider: LLMProvider,
        *,
        article_max_chars: int = 6000,
        score_config: CredibilityRiskScoringConfig | None = None,
        validator: VerificationAIExplanationValidator | None = None,
    ) -> None:
        self.provider = provider
        self.article_max_chars = max(1, article_max_chars)
        self.score_config = score_config or CredibilityRiskScoringConfig()
        self.validator = validator or VerificationAIExplanationValidator()

    def explain(
        self,
        event: EventContext,
        target: Article,
        response: VerificationResponse,
    ) -> VerificationAIExplanation:
        score_breakdown = self.build_score_breakdown(response)
        single_article = len(event.articles) == 1
        fallback = self._fallback(
            event,
            response,
            score_breakdown,
        )
        try:
            prompt = build_verification_explanation_prompt(
                self._prompt_payload(event, target, response, score_breakdown)
            )
            raw_output = self.provider.generate(prompt)
            if not isinstance(raw_output, str) or not raw_output.strip():
                return fallback
            decoded = self._decode_json_object(raw_output)
            normalized = self._normalize_llm_output(
                decoded,
                response,
                score_breakdown,
                event=event,
            )
            parsed = VerificationExplanationLLMOutput.model_validate(normalized)
            validated = self.validator.validate(
                parsed,
                response,
                score_breakdown,
                grounding_text=self._event_grounding(event),
            )
            if validated is None:
                return fallback
            if not self._has_llm_contribution(validated, fallback):
                return fallback
            validated = self._merge_with_fallback(
                validated,
                fallback,
                single_article=single_article,
            )
            trusted_limitations = list(self._scope_limitations(single_article))
            return validated.model_copy(update={"limitations": trusted_limitations})
        except (
            VerificationExplanationOutputFormatError,
            ValidationError,
            TimeoutError,
            ConnectionError,
        ):
            logger.warning(
                "verification_explanation_fallback provider=%s error_type=expected_failure",
                self.provider.name,
            )
            return fallback
        except Exception:
            logger.warning(
                "verification_explanation_fallback provider=%s error_type=unexpected_failure",
                self.provider.name,
            )
            return fallback

    def _decode_json_object(self, raw_output: str) -> dict:
        text = raw_output.strip()
        candidates = [text]
        if text.startswith("```"):
            first_newline = text.find("\n")
            closing_fence = text.rfind("```")
            if first_newline >= 0 and closing_fence > first_newline:
                candidates.insert(0, text[first_newline + 1 : closing_fence].strip())

        decoder = json.JSONDecoder()
        for candidate in candidates:
            try:
                decoded = json.loads(candidate)
            except json.JSONDecodeError:
                decoded = None
            if self._is_output_candidate(decoded):
                return decoded

            for index, character in enumerate(candidate):
                if character != "{":
                    continue
                try:
                    value, _ = decoder.raw_decode(candidate[index:])
                except json.JSONDecodeError:
                    continue
                if self._is_output_candidate(value):
                    return value
        raise VerificationExplanationOutputFormatError(
            "LLM output does not contain a JSON object"
        )

    def _normalize_llm_output(
        self,
        decoded: dict,
        response: VerificationResponse,
        score_breakdown: VerificationScoreBreakdown,
        *,
        event: EventContext | None = None,
    ) -> dict:
        claims = {item.claim_id: item for item in response.claim_results}
        normalized_claims = []
        for item in self._list_of_dicts(decoded.get("claim_explanations")):
            claim_id = self._positive_int(item.get("claim_id"))
            if claim_id is None:
                continue
            claim = claims.get(claim_id)
            claim_text = self._non_empty_text(item.get("claim"))
            conclusion = self._non_empty_text(item.get("conclusion"))
            explanation = self._non_empty_text(item.get("explanation"))
            if claim is not None:
                claim_text = claim_text or claim.claim
                conclusion = conclusion or self.validator.claim_conclusion(claim)
                explanation = explanation or claim.explanation or conclusion
            if not claim_text or not conclusion or not explanation:
                continue
            normalized_claims.append(
                {
                    "claim_id": claim_id,
                    "claim": claim_text,
                    "conclusion": conclusion,
                    "explanation": explanation,
                    "evidence": self._normalize_explained_evidence(
                        item.get("evidence")
                    ),
                }
            )

        normalized_reasons = []
        for item in self._list_of_dicts(decoded.get("why")):
            reason_type = self._non_empty_text(item.get("type"))
            title = self._non_empty_text(item.get("title"))
            explanation = self._non_empty_text(item.get("explanation"))
            if not reason_type or not title or not explanation:
                continue
            normalized_reasons.append(
                {
                    "type": reason_type,
                    "title": title,
                    "explanation": explanation,
                    "claim_ids": [
                        value
                        for raw in self._list_value(item.get("claim_ids"))
                        if (value := self._positive_int(raw)) is not None
                    ][:10],
                    "evidence_refs": self._normalize_evidence_refs(
                        item.get("evidence_refs"),
                        event,
                    ),
                }
            )

        return {
            "headline": self._non_empty_text(decoded.get("headline"))
            or self.validator.headline(response.overall_verdict),
            "conclusion": self._non_empty_text(decoded.get("conclusion"))
            or self.validator.overall_conclusion(response.overall_verdict),
            "why": normalized_reasons,
            "claim_explanations": normalized_claims,
            "score_explanation": self._non_empty_text(
                decoded.get("score_explanation")
            )
            or self.validator.score_explanation(score_breakdown),
            "limitations": [
                value
                for raw in self._list_value(decoded.get("limitations"))
                if (value := self._non_empty_text(raw)) is not None
            ][:12],
        }

    def _normalize_explained_evidence(self, value) -> list[dict]:
        result = []
        for item in self._list_of_dicts(value):
            news_id = item.get("news_id")
            source = item.get("source")
            quote = self._non_empty_text(item.get("quote"))
            explanation = self._non_empty_text(item.get("explanation"))
            if not isinstance(news_id, (int, str)) or not quote or not explanation:
                continue
            result.append(
                {
                    "news_id": news_id,
                    "source": source if isinstance(source, str) else "",
                    "quote": quote,
                    "explanation": explanation,
                }
            )
        return result[:20]

    @staticmethod
    def _list_value(value) -> list:
        if isinstance(value, list):
            return value
        return [] if value is None else [value]

    @classmethod
    def _is_output_candidate(cls, value) -> bool:
        return isinstance(value, dict) and any(
            key in value for key in cls._OUTPUT_FIELDS
        )

    @classmethod
    def _list_of_dicts(cls, value) -> list[dict]:
        return [item for item in cls._list_value(value) if isinstance(item, dict)]

    @staticmethod
    def _non_empty_text(value) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _positive_int(value) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        if isinstance(value, str) and value.strip().isdigit():
            parsed = int(value.strip())
            return parsed if parsed > 0 else None
        return None

    @staticmethod
    def _has_llm_contribution(
        validated: VerificationAIExplanation,
        fallback: VerificationAIExplanation,
    ) -> bool:
        return any(
            (
                validated.headline != fallback.headline,
                validated.conclusion != fallback.conclusion,
                validated.why != fallback.why,
                validated.claim_explanations != fallback.claim_explanations,
                validated.score_explanation != fallback.score_explanation,
                bool(validated.limitations),
            )
        )

    @staticmethod
    def _merge_with_fallback(
        validated: VerificationAIExplanation,
        fallback: VerificationAIExplanation,
        *,
        single_article: bool = False,
    ) -> VerificationAIExplanation:
        model_claims = {item.claim_id: item for item in validated.claim_explanations}
        claim_explanations = [
            model_claims.get(item.claim_id, item)
            for item in fallback.claim_explanations
        ]

        reasons = list(validated.why)
        if not reasons:
            covered_claim_ids = {
                claim_id for item in reasons for claim_id in item.claim_ids
            }
            reason_types = {
                item.type.casefold() for item in reasons if not item.claim_ids
            }
            for item in fallback.why:
                if item.claim_ids and any(
                    claim_id in covered_claim_ids for claim_id in item.claim_ids
                ):
                    continue
                if not item.claim_ids and item.type.casefold() in reason_types:
                    continue
                reasons.append(item)

        return validated.model_copy(
            update={
                "why": reasons[:12],
                "claim_explanations": claim_explanations[:10],
            }
        )

    def build_score_breakdown(
        self,
        response: VerificationResponse,
    ) -> VerificationScoreBreakdown:
        assessment = response.credibility_assessment
        if assessment is None:
            return VerificationScoreBreakdown(
                evidence_risk=0,
                evidence_weight=self.score_config.evidence_weight,
                evidence_contribution=0,
                source_risk=0,
                source_weight=self.score_config.source_weight,
                source_contribution=0,
                language_risk=0,
                language_weight=self.score_config.language_weight,
                language_contribution=0,
                total_risk_score=0,
            )
        evidence_risk = assessment.evidence_assessment.risk_score
        source_risk = assessment.source_assessment.risk_score
        language_risk = assessment.language_assessment.risk_score
        return VerificationScoreBreakdown(
            evidence_risk=evidence_risk,
            evidence_weight=self.score_config.evidence_weight,
            evidence_contribution=round(
                evidence_risk * self.score_config.evidence_weight, 1
            ),
            source_risk=source_risk,
            source_weight=self.score_config.source_weight,
            source_contribution=round(source_risk * self.score_config.source_weight, 1),
            language_risk=language_risk,
            language_weight=self.score_config.language_weight,
            language_contribution=round(
                language_risk * self.score_config.language_weight, 1
            ),
            total_risk_score=assessment.risk_score,
        )

    def _prompt_payload(
        self,
        event: EventContext,
        target: Article,
        response: VerificationResponse,
        score_breakdown: VerificationScoreBreakdown,
    ) -> dict:
        evidence_ids = {
            str(item.news_id)
            for claim in response.claim_results
            for item in [*claim.evidence, *claim.context_evidence]
        }
        relevant_articles = [
            article
            for article in event.articles
            if article is target
            or str(article.news_id) in evidence_ids
            or (
                article.news_id is not None
                and target.news_id is not None
                and str(article.news_id) == str(target.news_id)
            )
        ]
        article_payload = [
            {
                "news_id": article.news_id,
                "title": article.title,
                "content": article.content[: self.article_max_chars],
                "source": article.source,
                "url": article.url,
                "publish_time": article.publish_time,
                "platform": article.platform,
                "source_role": self._source_role(article),
                "is_official_input": article.is_official,
            }
            for article in relevant_articles
        ]
        articles_by_id = {
            str(article.news_id): article
            for article in relevant_articles
            if article.news_id is not None
        }
        evidence_source_context = []
        for item in response.evidence_source_assessments:
            article = articles_by_id.get(str(item.news_id))
            if article is None:
                continue
            evidence_source_context.append(
                {
                    "news_id": article.news_id,
                    "source": article.source,
                    "source_role": item.source_role,
                    "url": article.url,
                    "publish_time": article.publish_time,
                    "is_official_input": article.is_official,
                }
            )
        assessment = response.credibility_assessment
        source_assessment = assessment.source_assessment if assessment else None
        source_identity_confirmed = bool(
            source_assessment
            and source_assessment.status == "verified"
            and source_assessment.domain_match is True
        )
        return {
            "analysis_mode": (
                "single_article" if len(event.articles) == 1 else "multi_article"
            ),
            "event_and_articles": {
                "event_title": event.title,
                "event_summary_untrusted_background": event.summary,
                "target_news_id": target.news_id,
                "articles": article_payload,
            },
            "verified_results": {
                "overall_verdict": response.overall_verdict,
                "evidence_score": response.evidence_score,
                "score_type": response.score_type,
                "verification_coverage": response.verification_coverage,
                "claim_results": [
                    {
                        "claim_id": claim.claim_id,
                        "claim": claim.claim,
                        "verdict": claim.verdict,
                        "independent_source_count": claim.independent_source_count,
                        "evidence": [
                            item.model_dump(mode="json") for item in claim.evidence
                        ],
                        "context_evidence": [
                            item.model_dump(mode="json")
                            for item in claim.context_evidence
                        ],
                        "limitations": claim.limitations,
                    }
                    for claim in response.claim_results
                ],
                "evidence_source_context": evidence_source_context,
            },
            "deterministic_assessment": {
                "score_breakdown": score_breakdown.model_dump(mode="json"),
                "risk_label": assessment.risk_label if assessment else None,
                "assessment_confidence": (
                    assessment.assessment_confidence if assessment else None
                ),
                "evidence_assessment": (
                    assessment.evidence_assessment.model_dump(mode="json")
                    if assessment
                    else None
                ),
                "target_source_context": (
                    {
                        "source": target.source,
                        "source_role": self._source_role(target),
                        "url": target.url,
                        "publish_time": target.publish_time,
                        "is_official_input": target.is_official,
                        "source_identity": {
                            "confirmed": source_identity_confirmed,
                            "canonical_name": (
                                source_assessment.canonical_name
                                if source_identity_confirmed
                                else None
                            ),
                            "classification": (
                                source_assessment.source_category
                                if source_identity_confirmed
                                else None
                            ),
                            "ownership": (
                                source_assessment.ownership_type
                                if source_identity_confirmed
                                else None
                            ),
                            "basis": (
                                "来源名称与项目已知站点的域名一致"
                                if source_identity_confirmed
                                else None
                            ),
                        },
                    }
                    if assessment
                    else None
                ),
                "language_assessment": (
                    assessment.language_assessment.model_dump(mode="json")
                    if assessment
                    else None
                ),
                "semantic_assessment": (
                    assessment.semantic_assessment.model_dump(mode="json")
                    if assessment and assessment.semantic_assessment
                    else None
                ),
                "confidence_factors": {
                    "verification_coverage": response.verification_coverage,
                    "verifiable_claim_count": response.verifiable_claim_count,
                    "determinate_claim_count": response.determinate_claim_count,
                    "article_count": len(event.articles),
                },
            },
        }

    def _article_grounding(self, target: Article) -> str:
        """Text whose literal numbers may safely appear in model explanations."""
        return "\n".join(
            (
                target.title,
                target.content[: self.article_max_chars],
                target.source,
                target.publish_time,
            )
        )

    def _event_grounding(self, event: EventContext) -> str:
        """All supplied articles are valid grounding for comparative details."""
        return "\n".join(
            value
            for article in event.articles
            for value in (
                article.title,
                article.content[: self.article_max_chars],
                article.source,
                article.publish_time or "",
            )
            if value
        )

    @classmethod
    def _normalize_evidence_refs(
        cls,
        value,
        event: EventContext | None,
    ) -> list[int | str]:
        raw_refs = [
            item
            for item in cls._list_value(value)
            if isinstance(item, (int, str)) and str(item).strip()
        ]
        if event is None:
            return raw_refs[:20]
        actual_ids = {
            str(article.news_id): article.news_id
            for article in event.articles
            if article.news_id is not None
        }
        positional_ids = [
            article.news_id
            for article in event.articles
            if article.news_id is not None
        ]
        result = []
        for reference in raw_refs:
            key = str(reference).strip()
            if key in actual_ids:
                normalized = actual_ids[key]
            elif key.isdigit() and 1 <= int(key) <= len(positional_ids):
                normalized = positional_ids[int(key) - 1]
            else:
                continue
            if str(normalized) not in {str(item) for item in result}:
                result.append(normalized)
        return result[:20]

    def _fallback(
        self,
        event: EventContext,
        response: VerificationResponse,
        score_breakdown: VerificationScoreBreakdown,
    ) -> VerificationAIExplanation:
        single_article = len(event.articles) == 1
        claim_explanations = [
            (
                self._single_article_fallback_claim(item)
                if single_article
                else self._fallback_claim(item)
            )
            for item in response.claim_results
        ]
        reasons = (
            self._single_article_fallback_reasons(response)
            if single_article
            else [self._fallback_reason(item) for item in response.claim_results]
        )
        source_reason = self._source_reason(response)
        if source_reason is not None and not single_article:
            reasons.append(source_reason)
        if single_article:
            limitations = list(self._scope_limitations(True))
        else:
            limitations = list(self._scope_limitations(False))
        return VerificationAIExplanation(
            status="fallback",
            analysis_method="deterministic_fallback",
            headline=(
                self._single_article_fallback_headline(response)
                if single_article
                else self._multi_article_fallback_headline(event)
            ),
            conclusion=(
                self._single_article_fallback_conclusion(response)
                if single_article
                else self._multi_article_fallback_conclusion(
                    event,
                    response.overall_verdict,
                )
            ),
            why=reasons[:12],
            claim_explanations=claim_explanations[:10],
            score_breakdown=score_breakdown,
            score_explanation=self.validator.score_explanation(score_breakdown),
            limitations=limitations,
        )

    def _single_article_fallback_reasons(
        self,
        response: VerificationResponse,
    ) -> list[ExplanationReason]:
        reasons = []
        source_reason = self._source_reason(response)
        if source_reason is not None:
            reasons.append(source_reason)
        assessment = response.credibility_assessment
        if assessment is not None:
            language = assessment.language_assessment
            if language.flags:
                quotes = "、".join(
                    f"“{item.quote}”" for item in language.flags[:3]
                )
                explanation = (
                    f"标题或正文出现{quotes}等表达，确定性规则将其识别为需要关注的"
                    "绝对化、煽动性或归因风险；这会影响表达可信度，但不能单独证明内容虚假。"
                )
                title = "正文存在具体语言风险信号"
            else:
                explanation = (
                    "标题和正文未触发当前规则可识别的绝对化、煽动性、匿名归因或"
                    "情绪操纵表达，文本语气相对克制。"
                )
                title = "未发现明显的高风险表达"
            reasons.append(
                ExplanationReason(
                    type="language",
                    title=title,
                    explanation=explanation,
                )
            )
        if response.claim_results:
            claim = response.claim_results[0]
            reasons.append(
                ExplanationReason(
                    type="claim_quality",
                    title="正文包含可继续核验的具体主张",
                    explanation=(
                        f"文章明确提出“{claim.claim}”这一可核验表述，可以据此寻找"
                        "后续通报或其他报道进行比对。"
                    ),
                    claim_ids=[claim.claim_id],
                )
            )
        return reasons[:4]

    @staticmethod
    def _single_article_fallback_claim(
        claim: ClaimVerificationResult,
    ) -> ClaimAIExplanation:
        if claim.verdict == "not_verifiable":
            conclusion = "该表述以预测、建议或判断为主，当前不适合作确定性事实比较。"
            explanation = (
                f"文章中的“{claim.claim}”缺少可直接比较的确定性事实要素，"
                "因此本阶段只分析其表达方式。"
            )
        else:
            conclusion = "该主张已进入核验范围，当前仅能评估材料本身，尚待交叉核验。"
            explanation = (
                f"文章明确陈述“{claim.claim}”，该表述具有可核验的事实要素，"
                "可作为后续比对通报或其他报道的具体对象。"
            )
        return ClaimAIExplanation(
            claim_id=claim.claim_id,
            claim=claim.claim,
            conclusion=conclusion,
            explanation=explanation,
            evidence=[],
        )

    @staticmethod
    def _single_article_fallback_headline(
        response: VerificationResponse,
    ) -> str:
        assessment = response.credibility_assessment
        if assessment is None:
            return "已完成单篇新闻材料分析"
        source = assessment.source_assessment
        language = assessment.language_assessment
        if source.status == "verified" and not language.flags:
            return "来源可追溯，正文表达较为克制"
        if source.status == "verified":
            return "来源可追溯，正文表达仍有风险点"
        if not language.flags:
            return "来源信息较完整，正文表达较为克制"
        return "已从来源和正文表达识别可信度风险"

    @staticmethod
    def _single_article_fallback_conclusion(
        response: VerificationResponse,
    ) -> str:
        assessment = response.credibility_assessment
        if assessment is None:
            return "当前仅能评估这篇材料本身，其事实主张尚待交叉核验。"
        source = assessment.source_assessment
        language = assessment.language_assessment
        if source.status == "verified":
            source_text = "来源名称与对应站点一致，材料可追溯性较好"
        elif {
            "source_present",
            "url_hostname_present",
            "publish_time_present",
        } <= set(source.signals):
            source_text = "文章提供了来源、链接和发布时间，可进行基础溯源"
        else:
            source_text = "现有来源信息只能支持有限的材料溯源"
        language_text = (
            "正文存在需要结合原文语境关注的表达风险"
            if language.flags
            else "正文未发现当前规则可识别的明显高风险表达"
        )
        return (
            f"{source_text}，{language_text}；当前仅能据此评估材料本身，"
            "其事实主张尚待交叉核验。"
        )

    @staticmethod
    def _multi_article_fallback_headline(event: EventContext) -> str:
        subject = " ".join((event.title or "当前事件").split()).strip("#【】 ")
        return f"{subject[:42]}：多篇报道信息对比"

    @staticmethod
    def _multi_article_fallback_conclusion(
        event: EventContext,
        verdict: str,
    ) -> str:
        subject = " ".join((event.title or "当前事件").split()).strip("#【】 ")
        if verdict == "conflicting":
            finding = "当前材料中的支持与反驳材料并存，主要差异将在下方逐项呈现。"
        elif verdict == "supported":
            finding = "当前多篇报道对核心信息表述一致，具体共同点将在下方呈现。"
        elif verdict == "contradicted":
            finding = "当前多篇报道与目标表述存在明确差异，具体冲突将在下方呈现。"
        else:
            finding = "下方按共同信息、各篇补充和报道差异呈现分析结果。"
        return (
            f"本次已比较{len(event.articles)}篇围绕“{subject[:36]}”的材料，"
            f"{finding}"
        )

    def _fallback_claim(self, claim: ClaimVerificationResult) -> ClaimAIExplanation:
        evidence = [
            ExplainedEvidence(
                news_id=item.news_id,
                source=item.source,
                quote=item.quote,
                explanation=self._evidence_relation_text(item),
            )
            for item in [*claim.evidence, *claim.context_evidence]
        ]
        if claim.verdict == "supported":
            explanation = (
                f"目标主张得到{claim.independent_source_count}个独立来源支持。"
            )
        elif claim.verdict == "contradicted":
            explanation = (
                f"目标主张受到{claim.independent_source_count}个独立来源反驳。"
            )
        elif claim.verdict == "conflicting":
            explanation = "当前既有支持材料，也有反驳材料，来源说法并不一致。"
        elif claim.verdict == "insufficient_evidence":
            explanation = (
                f"现有{len(evidence)}篇相关材料可用于比较该主张的共同表述和细节差异。"
                if evidence
                else "现有材料可先用于梳理该主张的内容结构和后续关注点。"
            )
        else:
            explanation = "该表述属于预测、建议或主观判断，当前无法作为事实主张比较。"
        return ClaimAIExplanation(
            claim_id=claim.claim_id,
            claim=claim.claim,
            conclusion=self.validator.claim_conclusion(claim),
            explanation=explanation,
            evidence=evidence,
        )

    def _fallback_reason(self, claim: ClaimVerificationResult) -> ExplanationReason:
        refs = self._stable_refs(
            item.news_id for item in [*claim.evidence, *claim.context_evidence]
        )
        return ExplanationReason(
            type="evidence",
            title=f"核心信息：{claim.claim[:28]}",
            explanation=self._fallback_claim(claim).explanation,
            claim_ids=[claim.claim_id],
            evidence_refs=refs,
        )

    @staticmethod
    def _source_reason(response: VerificationResponse) -> ExplanationReason | None:
        assessment = response.credibility_assessment
        if assessment is None:
            return None
        source = assessment.source_assessment
        signals = set(source.signals)
        if (
            source.status == "verified"
            and source.domain_match is True
            and source.source_category == "官方新闻媒体"
        ):
            source_name = source.canonical_name or "该来源"
            explanation = (
                f"{source_name}的来源名称与对应站点链接一致，属于项目已知的官方新闻媒体，"
                "材料具有较好的身份可追溯性；来源性质本身不等于正文事实已经证实。"
            )
        elif source.status == "verified" and source.domain_match is True:
            source_name = source.canonical_name or "该来源"
            explanation = (
                f"{source_name}的来源名称与对应站点链接一致，材料身份可追溯性较好；"
                "这一因素不替代对正文主张的事实核验。"
            )
        elif {
            "source_present",
            "url_hostname_present",
            "publish_time_present",
        } <= signals:
            explanation = "目标文章提供了来源名称、链接和发布时间；这些信息用于说明材料的可追溯性，不替代事实证据。"
        elif "source_present" in signals:
            explanation = "目标文章提供了来源名称，但链接或发布时间信息不完整；来源元数据不替代事实证据。"
        else:
            explanation = "目标文章的来源名称、链接或发布时间信息较少；来源元数据不替代事实证据。"
        return ExplanationReason(
            type="source_identity",
            title="来源信息与事实证据需分别理解",
            explanation=explanation,
        )

    @staticmethod
    def _source_role(article: Article) -> str:
        values = " ".join(
            value.strip().casefold()
            for value in (article.source_type, article.account_type)
            if value and value.strip()
        )
        mappings = (
            (("government", "政务", "政府"), "government_notice"),
            (("regulator", "监管"), "regulator"),
            (("emergency", "应急"), "emergency_management"),
            (("fire", "消防"), "fire_rescue"),
            (("operator", "company", "企业", "运营"), "operator"),
            (("expert", "专家"), "expert_group"),
            (("witness", "目击"), "witness"),
            (("social", "自媒体", "社交"), "social_account"),
            (("media", "新闻媒体", "媒体"), "news_media"),
        )
        for markers, role in mappings:
            if any(marker in values for marker in markers):
                return role
        if "新闻" in article.platform:
            return "news_media"
        return "unknown"

    @staticmethod
    def _evidence_relation_text(item) -> str:
        relation = getattr(item, "stance", None) or getattr(item, "relation", None)
        source = item.source.strip() or "对应材料来源"
        quote = item.quote
        return {
            "supports": f"{source}原文“{quote}”与目标主张表述一致，因此构成支持证据。",
            "contradicts": f"{source}原文“{quote}”与目标主张直接冲突，因此构成反驳证据。",
            "related": f"{source}原文“{quote}”提供相关背景，但不直接支持或反驳目标主张。",
            "updates": f"{source}原文“{quote}”反映较晚的信息更新，不计为直接支持或反驳。",
        }[relation]

    @staticmethod
    def _stable_unique(values):
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @classmethod
    def _without_authentication_text(cls, values):
        return [
            value
            for value in values
            if not any(term in value for term in cls._AUTHENTICATION_TERMS)
        ]

    @classmethod
    def _without_repeated_single_source_text(cls, values):
        return [
            value
            for value in values
            if not any(term in value for term in cls._REPEATED_SINGLE_SOURCE_TERMS)
        ]

    @classmethod
    def _scope_limitations(cls, single_article: bool) -> tuple[str, ...]:
        return (
            (cls._SINGLE_ARTICLE_SCOPE_LIMITATION,)
            if single_article
            else cls._STANDARD_LIMITATIONS
        )

    @staticmethod
    def _stable_refs(values):
        result = []
        seen = set()
        for value in values:
            key = str(value)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result
