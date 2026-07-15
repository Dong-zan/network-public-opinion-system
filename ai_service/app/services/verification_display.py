import re

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
        "unknown": "新闻来源",
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
    _SINGLE_ARTICLE_UNCERTAINTY = (
        "本次为单篇材料审阅，重点分析关键主张、文内依据、逻辑与表达质量；"
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

    def build(
        self,
        event: EventContext,
        response: VerificationResponse,
    ) -> VerificationDisplayResult | None:
        explanation = response.ai_explanation
        if explanation is None:
            return None
        single_article = len(event.articles) == 1
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
                    else "新闻来源"
                )
                key = (news_key, item.source, item.quote)
                relation = getattr(item, "stance", None) or getattr(
                    item, "relation", "related"
                )
                evidence_explanation = (
                    self._relation_explanation(item)
                    if relation in {"related", "updates"}
                    else explained_evidence.get(
                        key,
                        self._relation_explanation(item),
                    )
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
        reason_values = [item.explanation for item in explanation.why]
        if not reason_values:
            reason_values = [
                item.explanation for item in explanation.claim_explanations
            ]
        for value in reason_values:
            normalized = self._content_focused_text(value)
            if (
                normalized
                and not (
                    single_article
                    and self._is_repeated_single_source_text(normalized)
                )
                and normalized not in evidence_explanations
                and normalized not in {explanation.headline, explanation.conclusion}
                and normalized not in reasons
            ):
                reasons.append(normalized)
        if single_article:
            uncertainties = [self._SINGLE_ARTICLE_UNCERTAINTY]
        else:
            uncertainties = [
                f"本次共比较{len(event.articles)}篇事件材料，重点呈现共同信息、"
                "报道差异与来源关系；结论对应当前材料范围。"
            ]
        conclusion = explanation.conclusion
        if conclusion.strip() == explanation.headline.strip():
            conclusion = VerificationAIExplanationValidator.overall_conclusion(
                response.overall_verdict
            )
        return VerificationDisplayResult(
            headline=explanation.headline,
            conclusion=conclusion,
            analysis_mode=(
                "single_article_audit"
                if single_article
                else "cross_source_verification"
            ),
            evidence_score_applicable=not single_article,
            reasons=reasons[:5],
            analysis_sections=explanation.why[:5],
            claim_reviews=explanation.claim_explanations[:10],
            evidence_cards=cards[:20],
            uncertainties=uncertainties,
        )

    @staticmethod
    def _relation_explanation(item) -> str:
        relation = getattr(item, "stance", None) or getattr(item, "relation", None)
        source = item.source.strip() or "对应材料来源"
        return {
            "supports": f"{source}的这段原文与目标主张表述一致，因此作为支持证据。",
            "contradicts": f"{source}的这段原文与目标主张存在直接冲突，因此作为反驳证据。",
            "updates": f"{source}的这段原文补充了较晚时点的信息，可用于梳理事件变化。",
            "related": f"{source}的这段原文补充了相关背景和细节，可用于比较不同报道的侧重点。",
        }.get(relation, f"{source}的这段原文用于说明当前证据关系。")

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _content_focused_text(value: str) -> str:
        limiting_patterns = (
            r"[^。！？]*未提供(?:主办方|官方|猫眼)[^。！？]*[。！？]",
            r"[^。！？]*缺乏(?:独立|官方|直接)[^。！？]*[。！？]",
            r"[^。！？]*无法独立[^。！？]*[。！？]",
            r"[^。！？]*(?:尚待|仍需|需要)[^。！？]{0,30}(?:核实|确认)[^。！？]*[。！？]",
            r"[^。！？]*不替代事实证据[。！？]?",
            r"[^。！？]*(?:官方输入|上游来源角色标记)[^。！？]*[。！？]",
            r"[^。！？]*(?:证据强度为|启发式评分|风险标签)[^。！？]*[。！？]",
        )
        normalized = " ".join(value.split())
        normalized = re.sub(
            r"([一二三四五六七八九十\d]+)篇独立来源",
            r"\1篇不同材料",
            normalized,
        )
        for pattern in limiting_patterns:
            normalized = re.sub(pattern, "", normalized)
        return normalized.strip()

    @classmethod
    def _without_authentication_text(cls, values: list[str]) -> list[str]:
        return [
            value
            for value in values
            if not any(term in value for term in cls._AUTHENTICATION_TERMS)
        ]

    @classmethod
    def _is_repeated_single_source_text(cls, value: str) -> bool:
        return any(term in value for term in cls._REPEATED_SINGLE_SOURCE_TERMS)

    @classmethod
    def _without_repeated_single_source_text(
        cls,
        values: list[str],
    ) -> list[str]:
        return [
            value
            for value in values
            if not cls._is_repeated_single_source_text(value)
        ]
