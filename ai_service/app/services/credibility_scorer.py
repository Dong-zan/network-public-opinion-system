from dataclasses import dataclass

from app.schemas.verification import (
    EvidenceAssessment,
    LanguageAssessment,
    SourceAssessment,
    VerificationResponse,
)


@dataclass(frozen=True)
class CredibilityRiskScoringConfig:
    version: str = "credibility-risk-v1.1"
    evidence_weight: float = 0.60
    source_weight: float = 0.25
    language_weight: float = 0.15
    low_max: float = 24.9
    caution_max: float = 49.9
    suspicious_max: float = 74.9


@dataclass(frozen=True)
class CredibilityScore:
    evidence: EvidenceAssessment
    risk_score: float
    risk_label: str


class CredibilityRiskScorer:
    def __init__(self, config: CredibilityRiskScoringConfig | None = None) -> None:
        self.config = config or CredibilityRiskScoringConfig()

    def score(
        self,
        verification: VerificationResponse,
        source: SourceAssessment,
        language: LanguageAssessment,
    ) -> CredibilityScore:
        evidence_risk = self._evidence_risk(verification.overall_verdict, verification.evidence_score)
        independent_count = max((item.independent_source_count for item in verification.claim_results), default=0)
        evidence = EvidenceAssessment(
            verdict=verification.overall_verdict,
            evidence_score=verification.evidence_score,
            risk_score=evidence_risk,
            independent_source_count=independent_count,
            explanation=self._evidence_explanation(verification.overall_verdict, verification.evidence_score),
        )
        raw = round(
            evidence_risk * self.config.evidence_weight
            + source.risk_score * self.config.source_weight
            + language.risk_score * self.config.language_weight,
            1,
        )
        if verification.overall_verdict == "contradicted" and verification.evidence_score >= 70:
            raw = max(raw, 75.0)
        label = self._label(raw)
        if verification.overall_verdict in {"conflicting", "insufficient_evidence"} and label == "low":
            label = "caution" if verification.overall_verdict == "conflicting" else "suspicious"
        if verification.overall_verdict == "not_verifiable":
            label = "not_assessable"
        return CredibilityScore(evidence=evidence, risk_score=raw, risk_label=label)

    @staticmethod
    def _evidence_risk(verdict: str, evidence_score: float) -> float:
        if verdict == "supported":
            return round(min(30.0, max(5.0, 30.0 - evidence_score * 0.25)), 1)
        if verdict == "contradicted":
            return round(min(100.0, max(70.0, 65.0 + evidence_score * 0.35)), 1)
        if verdict == "conflicting":
            return round(min(90.0, max(55.0, 55.0 + evidence_score * 0.25)), 1)
        if verdict == "insufficient_evidence":
            return 55.0
        return 50.0

    def _label(self, score: float) -> str:
        if score <= self.config.low_max:
            return "low"
        if score <= self.config.caution_max:
            return "caution"
        if score <= self.config.suspicious_max:
            return "suspicious"
        return "high"

    @staticmethod
    def _evidence_explanation(verdict: str, score: float) -> str:
        names = {
            "supported": "当前输入材料中的多来源表述较为一致",
            "contradicted": "当前输入材料中存在较强的反驳证据",
            "conflicting": "当前输入材料中存在相互冲突的证据",
            "insufficient_evidence": "当前独立来源证据不足",
            "not_verifiable": "当前未提取到可确定性比较的事实主张",
        }
        return f"{names[verdict]}；启发式证据强度为{score:g}，不是文章真实性概率。"
