from app.schemas.event import EventContext
from app.schemas.verification import VerificationResponse
from app.schemas.verification_explanation import (
    VerificationDisplayResult,
    VerificationEvidenceCard,
)
from app.services.verification_explanation_validator import (
    VerificationAIExplanationValidator,
)


class VerificationDisplayBuilder:
    _ROLE_LABELS = {
        "government_notice": "政务发布",
        "regulator": "监管机构",
        "emergency_management": "应急管理机构",
        "fire_rescue": "消防救援机构",
        "operator": "运营主体",
        "expert_group": "专家机构",
        "news_media": "新闻媒体",
        "witness": "目击者",
        "social_account": "社交账号",
        "anonymous_source": "匿名来源",
        "unknown": "来源类型未明确",
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
        "来源身份已验证",
        "来源身份已经确认",
    )
    _STANDARD_UNCERTAINTIES = (
        "本次核验仅使用当前输入的新闻材料，没有联网检索其他报道。",
        "当前结论表示输入材料之间的证据关系，不代表最终权威认定。",
    )

    def build(
        self,
        event: EventContext,
        response: VerificationResponse,
    ) -> VerificationDisplayResult | None:
        explanation = response.ai_explanation
        if explanation is None:
            return None
        source_assessments = {
            str(item.news_id): item for item in response.evidence_source_assessments
        }
        explained_evidence = {
            (str(item.news_id), item.source, item.quote): item.explanation
            for claim in explanation.claim_explanations
            for item in claim.evidence
        }
        cards = []
        seen_news_ids = set()
        seen_quotes = set()
        evidence_explanations = set()
        for claim in response.claim_results:
            for item in [*claim.evidence, *claim.context_evidence]:
                news_key = str(item.news_id)
                quote_key = " ".join(item.quote.split())
                if news_key in seen_news_ids or quote_key in seen_quotes:
                    continue
                seen_news_ids.add(news_key)
                seen_quotes.add(quote_key)
                source_assessment = source_assessments.get(news_key)
                source_description = (
                    self._ROLE_LABELS[source_assessment.source_role]
                    if source_assessment is not None
                    else "来源类型未明确"
                )
                key = (news_key, item.source, item.quote)
                evidence_explanation = explained_evidence.get(
                    key,
                    self._relation_explanation(item),
                )
                evidence_explanations.add(evidence_explanation)
                cards.append(
                    VerificationEvidenceCard(
                        news_id=item.news_id,
                        source=item.source,
                        source_description=source_description,
                        quote=item.quote,
                        stance=getattr(item, "stance", None)
                        or getattr(item, "relation", "related"),
                        explanation=evidence_explanation,
                        url=item.url,
                    )
                )

        reasons = []
        for value in [
            *(item.explanation for item in explanation.why),
            *(item.explanation for item in explanation.claim_explanations),
        ]:
            normalized = value.strip()
            if (
                normalized
                and normalized not in evidence_explanations
                and normalized not in {explanation.headline, explanation.conclusion}
                and normalized not in reasons
            ):
                reasons.append(normalized)
        uncertainties = self._stable_unique(
            [
                *self._STANDARD_UNCERTAINTIES,
                *self._without_authentication_text(explanation.limitations),
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
        conclusion = explanation.conclusion
        if conclusion.strip() == explanation.headline.strip():
            conclusion = VerificationAIExplanationValidator.overall_conclusion(
                response.overall_verdict
            )
        return VerificationDisplayResult(
            headline=explanation.headline,
            conclusion=conclusion,
            reasons=reasons[:12],
            evidence_cards=cards[:20],
            uncertainties=uncertainties,
        )

    @staticmethod
    def _relation_explanation(item) -> str:
        relation = getattr(item, "stance", None) or getattr(item, "relation", None)
        source = item.source.strip() or f"news_id={item.news_id}对应来源"
        return {
            "supports": f"{source}的这段原文与目标主张表述一致，因此作为支持证据。",
            "contradicts": f"{source}的这段原文与目标主张存在直接冲突，因此作为反驳证据。",
            "updates": f"{source}的这段原文提供了较晚时点的信息更新，不作为直接支持或反驳。",
            "related": f"{source}的这段原文与目标主张相关，但不足以直接支持或反驳。",
        }.get(relation, f"{source}的这段原文用于说明当前证据关系。")

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @classmethod
    def _without_authentication_text(cls, values: list[str]) -> list[str]:
        return [
            value
            for value in values
            if not any(term in value for term in cls._AUTHENTICATION_TERMS)
        ]
