import json
import re
from decimal import Decimal, InvalidOperation

from app.schemas.verification import ClaimVerificationResult, VerificationResponse
from app.schemas.verification_explanation import (
    ClaimAIExplanation,
    ExplainedEvidence,
    ExplanationReason,
    VerificationAIExplanation,
    VerificationExplanationLLMOutput,
    VerificationScoreBreakdown,
)


class VerificationAIExplanationValidator:
    _USER_TEXT_REPLACEMENTS = (
        (
            "该来源被标记为is_official_input，仅表示上游输入标记，不构成权威性证明。",
            "输入中的来源角色只用于说明材料背景，不构成权威性证明。",
        ),
        ("（government_notice）", ""),
        ("(government_notice)", ""),
        ("（news_media）", ""),
        ("(news_media)", ""),
        ("government_notice", "政务发布"),
        ("news_media", "新闻媒体"),
        ("emergency_management", "应急管理机构"),
        ("fire_rescue", "消防救援机构"),
        ("expert_group", "专家机构"),
        ("social_account", "社交账号"),
        ("anonymous_source", "匿名来源"),
        ("regulator", "监管机构"),
        ("operator", "运营主体"),
        ("witness", "目击者"),
        ("is_official_input", "上游来源角色标记"),
        ("source_role", "来源类型"),
    )
    _INTERNAL_FIELD_TERMS = (
        "government_notice",
        "news_media",
        "emergency_management",
        "fire_rescue",
        "expert_group",
        "social_account",
        "anonymous_source",
        "is_official_input",
        "source_role",
        "account_type",
        "source_type",
        "identity_status",
        "registered_source",
        "domain_match",
        "metadata_coverage",
        "provider_name",
    )
    _STRONG_SOURCE_IDENTITY_PHRASES = (
        "权威来源已确认",
        "来源身份已经确认",
        "来源身份已确认",
        "官方来源已确认",
        "已验证权威来源",
    )
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
    _EVIDENCE_REASON_TYPES = {
        "evidence",
        "support",
        "contradiction",
        "conflict",
        "证据",
        "支持证据",
        "反驳证据",
        "冲突证据",
    }

    def validate(
        self,
        output: VerificationExplanationLLMOutput,
        response: VerificationResponse,
        score_breakdown: VerificationScoreBreakdown,
    ) -> VerificationAIExplanation | None:
        claims = {item.claim_id: item for item in response.claim_results}
        evidence_by_claim = self._evidence_by_claim(response.claim_results)
        all_evidence_ids = {
            str(item.news_id)
            for values in evidence_by_claim.values()
            for item in values
        }
        allowed_numbers = self._number_tokens(
            json.dumps(response.model_dump(mode="json"), ensure_ascii=False)
            + json.dumps(score_breakdown.model_dump(mode="json"), ensure_ascii=False)
        )
        score_numbers = self._number_tokens(
            json.dumps(score_breakdown.model_dump(mode="json"), ensure_ascii=False)
        )
        source_identity_confirmed = self._source_identity_confirmed(response)
        verified_evidence_ids = {
            str(item.news_id)
            for item in response.evidence_source_assessments
            if item.identity_status == "verified" and item.domain_match is True
        }

        reasons = []
        for reason in output.why:
            title = self._naturalize_user_text(reason.title)
            explanation = self._naturalize_user_text(reason.explanation)
            claim_ids = self._stable_unique_ints(
                claim_id for claim_id in reason.claim_ids if claim_id in claims
            )
            evidence_refs = self._stable_unique_refs(
                reference
                for reference in reason.evidence_refs
                if str(reference) in all_evidence_ids
            )
            if reason.type.casefold() in self._EVIDENCE_REASON_TYPES and not evidence_refs:
                continue
            if not self._text_is_safe(
                (title, explanation),
                allowed_numbers,
                source_identity_confirmed
                or bool(evidence_refs)
                and all(str(reference) in verified_evidence_ids for reference in evidence_refs),
            ):
                continue
            reasons.append(
                ExplanationReason(
                    type=reason.type,
                    title=title,
                    explanation=explanation,
                    claim_ids=claim_ids,
                    evidence_refs=evidence_refs,
                )
            )

        claim_explanations = []
        for item in output.claim_explanations:
            claim = claims.get(item.claim_id)
            if claim is None:
                continue
            evidence = self._validated_evidence(
                item.evidence,
                evidence_by_claim[item.claim_id],
                allowed_numbers,
                verified_evidence_ids,
            )
            if claim.verdict in {"supported", "contradicted", "conflicting"} and not evidence:
                continue
            item_explanation = self._naturalize_user_text(item.explanation)
            item_conclusion = self._naturalize_user_text(item.conclusion)
            if not self._text_is_safe(
                (item_explanation,),
                allowed_numbers,
                source_identity_confirmed,
            ):
                continue
            claim_explanations.append(
                ClaimAIExplanation(
                    claim_id=claim.claim_id,
                    claim=claim.claim,
                    conclusion=(
                        item_conclusion
                        if self._text_is_safe(
                            (item_conclusion,),
                            allowed_numbers,
                            source_identity_confirmed,
                        )
                        and self._conclusion_matches_verdict(
                            item_conclusion,
                            claim.verdict,
                        )
                        else self.claim_conclusion(claim)
                    ),
                    explanation=item_explanation,
                    evidence=evidence,
                )
            )

        if not reasons and not claim_explanations:
            return None
        proposed_headline = self._naturalize_user_text(output.headline)
        headline = (
            proposed_headline
            if self._text_is_safe((proposed_headline,), allowed_numbers, source_identity_confirmed)
            else self.headline(response.overall_verdict)
        )
        proposed_score_explanation = self._naturalize_user_text(
            output.score_explanation
        )
        score_explanation = (
            proposed_score_explanation
            if self._text_is_safe(
                (proposed_score_explanation,),
                score_numbers,
                source_identity_confirmed,
            )
            else self.score_explanation(score_breakdown)
        )
        limitations = [
            normalized
            for value in self._stable_unique_text(output.limitations)
            if (normalized := self._naturalize_user_text(value))
            if self._text_is_safe((normalized,), allowed_numbers, source_identity_confirmed)
        ][:12]
        proposed_conclusion = self._naturalize_user_text(output.conclusion)
        conclusion = (
            proposed_conclusion
            if self._text_is_safe(
                (proposed_conclusion,),
                allowed_numbers,
                source_identity_confirmed,
            )
            and self._conclusion_matches_verdict(
                proposed_conclusion,
                response.overall_verdict,
            )
            else self.overall_conclusion(response.overall_verdict)
        )
        return VerificationAIExplanation(
            status="success",
            analysis_method="llm",
            headline=headline,
            conclusion=conclusion,
            why=reasons[:12],
            claim_explanations=claim_explanations[:10],
            score_breakdown=score_breakdown,
            score_explanation=score_explanation,
            limitations=limitations,
        )

    @classmethod
    def _validated_evidence(
        cls,
        proposed,
        valid,
        allowed_numbers,
        verified_evidence_ids,
    ):
        valid_by_key = {
            (str(item.news_id), item.source, item.quote): item
            for item in valid
        }
        result = []
        seen = set()
        for item in proposed:
            key = (str(item.news_id), item.source, item.quote)
            if key not in valid_by_key or key in seen:
                continue
            valid_item = valid_by_key[key]
            explanation = cls._naturalize_user_text(item.explanation)
            if not cls._text_is_safe(
                (explanation,),
                allowed_numbers,
                str(item.news_id) in verified_evidence_ids,
            ):
                explanation = cls._evidence_relation_text(valid_item)
            seen.add(key)
            result.append(
                ExplainedEvidence(
                    news_id=valid_item.news_id,
                    source=valid_item.source,
                    quote=valid_item.quote,
                    explanation=explanation,
                )
            )
        return result

    @staticmethod
    def _evidence_relation_text(item) -> str:
        relation = getattr(item, "stance", None) or getattr(item, "relation", None)
        source = item.source.strip() or f"news_id={item.news_id}对应来源"
        return {
            "supports": f"{source}的逐字材料与目标主张表述一致，因此构成支持证据。",
            "contradicts": f"{source}的逐字材料与目标主张直接冲突，因此构成反驳证据。",
            "related": f"{source}的逐字材料提供相关背景，但不直接支持或反驳目标主张。",
            "updates": f"{source}的逐字材料反映信息更新，不计为直接支持或反驳。",
        }[relation]

    @staticmethod
    def _evidence_by_claim(claims):
        return {
            claim.claim_id: [*claim.evidence, *claim.context_evidence]
            for claim in claims
        }

    @classmethod
    def _text_is_safe(cls, values, allowed_numbers, source_identity_confirmed):
        for value in values:
            if not cls._number_tokens(value) <= allowed_numbers:
                return False
            if any(term in value for term in cls._AUTHENTICATION_TERMS):
                return False
            if any(term in value.casefold() for term in cls._INTERNAL_FIELD_TERMS):
                return False
            if any(
                phrase in value for phrase in cls._STRONG_SOURCE_IDENTITY_PHRASES
            ):
                return False
        return True

    @classmethod
    def _naturalize_user_text(cls, value: str) -> str:
        normalized = value.strip()
        for source, replacement in cls._USER_TEXT_REPLACEMENTS:
            normalized = re.sub(
                re.escape(source),
                replacement,
                normalized,
                flags=re.IGNORECASE,
            )
        normalized = normalized.replace("（ ）", "").replace("()", "")
        return " ".join(normalized.split())

    @staticmethod
    def _source_identity_confirmed(response: VerificationResponse) -> bool:
        assessment = response.credibility_assessment
        if assessment is None:
            return False
        source = assessment.source_assessment
        return source.status == "verified" and source.domain_match is True

    @staticmethod
    def _conclusion_matches_verdict(value: str, verdict: str) -> bool:
        normalized = value.strip()
        markers = {
            "supported": ("支持", "一致", "相符"),
            "contradicted": ("反驳", "矛盾", "不一致", "冲突"),
            "conflicting": ("冲突", "说法不一", "支持与反驳"),
            "insufficient_evidence": ("证据不足", "缺少", "不足以", "无法确认"),
            "not_verifiable": ("不可核验", "无法核验", "不能核验", "无法形成"),
        }[verdict]
        blocked = {
            "supported": ("被反驳", "证据不足", "已经被证明虚假", "存在直接冲突"),
            "contradicted": ("得到多来源支持", "材料表述一致", "已经证实为真"),
            "conflicting": ("只有支持", "只有反驳", "已经最终确认"),
            "insufficient_evidence": ("已经证实", "得到多来源支持", "受到多来源反驳"),
            "not_verifiable": ("已经证实", "得到多来源支持", "受到多来源反驳"),
        }[verdict]
        return any(marker in normalized for marker in markers) and not any(
            marker in normalized for marker in blocked
        )

    @staticmethod
    def _number_tokens(value: str) -> set[str]:
        result = set()
        for token in re.findall(r"\d+(?:\.\d+)?", value):
            try:
                result.add(str(Decimal(token).normalize()))
            except InvalidOperation:
                continue
        return result

    @staticmethod
    def _stable_unique_text(values):
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _stable_unique_ints(values):
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    @staticmethod
    def _stable_unique_refs(values):
        result = []
        seen = set()
        for value in values:
            key = str(value)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def headline(verdict: str) -> str:
        return {
            "supported": "多来源证据与目标主张一致",
            "contradicted": "多来源证据反驳目标主张",
            "conflicting": "不同来源对目标主张存在冲突",
            "insufficient_evidence": "现有独立证据不足",
            "not_verifiable": "当前表述暂不可核验",
        }[verdict]

    @staticmethod
    def overall_conclusion(verdict: str) -> str:
        return {
            "supported": "当前输入中的多来源材料对目标主张表述一致，但这不等于现实事实已经得到永久确认。",
            "contradicted": "当前输入中的多来源材料对目标主张形成反驳，但该结论仍受现有材料范围限制。",
            "conflicting": "当前输入中的支持与反驳材料并存，不能选择其中一种说法作为最终事实。",
            "insufficient_evidence": "当前缺少足够独立证据形成稳定结论，证据不足不等于文章已经被证明虚假。",
            "not_verifiable": "当前没有可确定性比较的事实主张，无法形成事实核验结论。",
        }[verdict]

    @staticmethod
    def claim_conclusion(claim: ClaimVerificationResult) -> str:
        return {
            "supported": "该主张在当前输入材料中得到多来源支持。",
            "contradicted": "该主张在当前输入材料中受到多来源反驳。",
            "conflicting": "该主张在当前输入材料中同时存在支持和反驳。",
            "insufficient_evidence": "该主张缺少足够独立证据，暂不能确认或反驳。",
            "not_verifiable": "该表述不属于当前阶段可确定性核验的事实主张。",
        }[claim.verdict]

    @staticmethod
    def score_explanation(score: VerificationScoreBreakdown) -> str:
        explanation = (
            f"证据、来源和语言三个维度的风险贡献分别为"
            f"{score.evidence_contribution:g}、{score.source_contribution:g}和"
            f"{score.language_contribution:g}，最终确定性综合风险分为"
            f"{score.total_risk_score:g}。该分数不是文章真实性概率。"
        )
        contribution_total = round(
            score.evidence_contribution
            + score.source_contribution
            + score.language_contribution,
            1,
        )
        if contribution_total != score.total_risk_score:
            explanation += "最终分数同时应用了既有确定性裁决规则中的风险下限。"
        return explanation
