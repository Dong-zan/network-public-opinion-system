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


class VerificationExplanationService:
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
        "本次核验仅使用当前输入的新闻材料，没有联网检索其他报道。",
        "当前结论表示输入材料之间的证据关系，不代表最终权威认定。",
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
        fallback = self._fallback(response, score_breakdown)
        try:
            prompt = build_verification_explanation_prompt(
                self._prompt_payload(event, target, response, score_breakdown)
            )
            raw_output = self.provider.generate(prompt)
            if not isinstance(raw_output, str) or not raw_output.strip():
                return fallback
            decoded = json.loads(raw_output)
            parsed = VerificationExplanationLLMOutput.model_validate(decoded)
            validated = self.validator.validate(parsed, response, score_breakdown)
            if validated is None:
                return fallback
            trusted_limitations = self._stable_unique(
                [
                    *self._STANDARD_LIMITATIONS,
                    *self._without_authentication_text(validated.limitations),
                    *self._without_authentication_text(response.limitations),
                ]
            )[:12]
            return validated.model_copy(update={"limitations": trusted_limitations})
        except (json.JSONDecodeError, ValidationError, TimeoutError, ConnectionError):
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
        return {
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
                        "metadata_coverage": (
                            assessment.source_assessment.metadata_coverage
                        ),
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
                    "source_metadata_coverage": (
                        assessment.source_assessment.metadata_coverage
                        if assessment
                        else None
                    ),
                },
            },
        }

    def _fallback(
        self,
        response: VerificationResponse,
        score_breakdown: VerificationScoreBreakdown,
    ) -> VerificationAIExplanation:
        claim_explanations = [
            self._fallback_claim(item) for item in response.claim_results
        ]
        reasons = [self._fallback_reason(item) for item in response.claim_results]
        source_reason = self._source_reason(response)
        if source_reason is not None:
            reasons.append(source_reason)
        limitations = self._stable_unique(
            [
                *self._STANDARD_LIMITATIONS,
                *self._without_authentication_text(response.limitations),
                *(
                    limitation
                    for claim in response.claim_results
                    for limitation in self._without_authentication_text(
                        claim.limitations
                    )
                ),
            ]
        )[:12]
        return VerificationAIExplanation(
            status="fallback",
            analysis_method="deterministic_fallback",
            headline=self.validator.headline(response.overall_verdict),
            conclusion=self.validator.overall_conclusion(response.overall_verdict),
            why=reasons[:12],
            claim_explanations=claim_explanations[:10],
            score_breakdown=score_breakdown,
            score_explanation=self.validator.score_explanation(score_breakdown),
            limitations=limitations,
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
                "当前只有有限证据，尚不足以独立确认或反驳该主张。"
                if evidence
                else "当前输入中没有其他独立新闻可以确认或反驳该主张。"
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
            title=f"主张{claim.claim_id}的证据关系",
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
        if {
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
        source = item.source.strip() or f"news_id={item.news_id}对应来源"
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
