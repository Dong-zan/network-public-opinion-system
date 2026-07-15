from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.news_identity import normalized_news_id
from app.schemas.event import EventContext
from app.schemas.verification_explanation import (
    VerificationAIExplanation,
    VerificationDisplayResult,
)


VerificationVerdict = Literal[
    "supported",
    "contradicted",
    "conflicting",
    "insufficient_evidence",
    "not_verifiable",
]
EvidenceStance = Literal["supports", "contradicts"]
ContextEvidenceRelation = Literal["related", "updates"]
CredibilityMethod = Literal["deterministic", "hybrid", "deterministic_fallback"]
CredibilityRiskLabel = Literal["low", "caution", "suspicious", "high", "not_assessable"]
SourceAssessmentStatus = Literal["verified", "partially_verified", "unknown", "mismatch"]
LanguageRiskLevel = Literal["low", "medium", "high", "unknown"]
LanguageRiskType = Literal[
    "absolute_claim",
    "sensational_language",
    "anonymous_attribution",
    "emotional_manipulation",
    "conspiracy_claim",
    "unsupported_causality",
    "title_body_mismatch",
    "preliminary_as_confirmed",
    "uncertainty_removed",
    "unsupported_generalization",
]
SemanticAssessmentStatus = Literal["success", "fallback"]
SemanticAssessmentMethod = Literal["llm", "deterministic_fallback"]
SourceRole = Literal[
    "government_notice",
    "regulator",
    "emergency_management",
    "fire_rescue",
    "operator",
    "expert_group",
    "news_media",
    "witness",
    "social_account",
    "anonymous_source",
    "unknown",
]
RoleRelevance = Literal["high", "medium", "low", "unknown"]
RoleAssessmentBasis = Literal["publisher_metadata", "attribution_quote", "unknown"]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventContext
    target_news_id: int | str
    max_claims: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def validate_unique_news_ids(self):
        seen = set()
        for article in self.event.articles:
            key = normalized_news_id(article.news_id)
            if key is None:
                continue
            if key in seen:
                raise ValueError("核验事件中的非空news_id必须唯一")
            seen.add(key)
        return self


class VerificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: int | str
    source: str = ""
    url: str = ""
    quote: NonEmptyText
    stance: EvidenceStance
    reason_code: str | None = None
    relevance_score: float | None = Field(default=None, ge=0, le=1)


class VerificationContextEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: int | str
    source: str = ""
    url: str = ""
    quote: NonEmptyText
    relation: ContextEvidenceRelation
    reason_code: str | None = None
    relevance_score: float | None = Field(default=None, ge=0, le=1)


class ClaimVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: int = Field(ge=1)
    claim: NonEmptyText
    verdict: VerificationVerdict
    independent_source_count: int = Field(ge=0)
    evidence: list[VerificationEvidence] = Field(default_factory=list)
    context_evidence: list[VerificationContextEvidence] = Field(default_factory=list)
    limitations: list[NonEmptyText] = Field(default_factory=list)
    evidence_score: float | None = Field(default=None, ge=0, le=100)
    explanation: str | None = None


class EvidenceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: VerificationVerdict
    evidence_score: float = Field(ge=0, le=100)
    risk_score: float = Field(ge=0, le=100)
    independent_source_count: int = Field(ge=0)
    explanation: NonEmptyText


class SourceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SourceAssessmentStatus
    traceability_score: float | None = Field(default=None, ge=0, le=100)
    risk_score: float = Field(ge=0, le=100)
    registered_source: bool | None = None
    canonical_name: NonEmptyText | None = None
    hostname: NonEmptyText | None = None
    domain_match: bool | None = None
    metadata_coverage: float = Field(ge=0, le=100)
    signals: list[NonEmptyText] = Field(default_factory=list)


class EvidenceSourceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: int | str
    source: str = ""
    source_role: SourceRole = "unknown"
    identity_status: SourceAssessmentStatus = "unknown"
    registered_source: bool | None = None
    domain_match: bool | None = None
    metadata_coverage: float = Field(ge=0, le=100)
    explanation: NonEmptyText


class LanguageRiskFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: LanguageRiskType
    severity: int = Field(ge=1, le=3)
    quote: NonEmptyText
    explanation: NonEmptyText


class LanguageAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: LanguageRiskLevel
    risk_score: float = Field(ge=0, le=100)
    analysis_method: Literal["deterministic"] = "deterministic"
    flags: list[LanguageRiskFlag] = Field(default_factory=list)


class SemanticLanguageRiskFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: LanguageRiskType
    severity: int = Field(ge=1, le=3)
    quote: NonEmptyText
    explanation: NonEmptyText
    related_claim_id: int | None = Field(default=None, ge=1)
    evidence_quote: NonEmptyText | None = None
    evidence_news_id: int | str | None = None
    comparison_quote: NonEmptyText | None = None


class ClaimSourceRoleAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: int = Field(ge=1)
    publisher_role: SourceRole = "unknown"
    attributed_role: SourceRole = "unknown"
    role_relevance: RoleRelevance = "unknown"
    quote: NonEmptyText | None = None
    explanation: NonEmptyText
    basis: RoleAssessmentBasis = "unknown"


class SemanticCredibilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SemanticAssessmentStatus
    analysis_method: SemanticAssessmentMethod
    language_flags: list[SemanticLanguageRiskFlag] = Field(default_factory=list, max_length=12)
    source_role_assessments: list[ClaimSourceRoleAssessment] = Field(default_factory=list, max_length=12)
    limitations: list[NonEmptyText] = Field(default_factory=list)


class CredibilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: NonEmptyText
    analysis_method: CredibilityMethod
    risk_label: CredibilityRiskLabel
    risk_score: float = Field(ge=0, le=100)
    assessment_confidence: float = Field(ge=0, le=100)
    evidence_assessment: EvidenceAssessment
    source_assessment: SourceAssessment
    language_assessment: LanguageAssessment
    decisive_factors: list[NonEmptyText] = Field(default_factory=list)
    summary: NonEmptyText
    warnings: list[NonEmptyText] = Field(default_factory=list)
    semantic_assessment: SemanticCredibilityAssessment | None = None


class VerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_news_id: int | str
    overall_verdict: VerificationVerdict
    evidence_score: float = Field(ge=0, le=100)
    score_type: Literal["heuristic_evidence_score"] = "heuristic_evidence_score"
    claim_results: list[ClaimVerificationResult] = Field(default_factory=list)
    risk_flags: list[NonEmptyText] = Field(default_factory=list)
    limitations: list[NonEmptyText] = Field(default_factory=list)
    verifiable_claim_count: int = Field(default=0, ge=0)
    determinate_claim_count: int = Field(default=0, ge=0)
    verification_coverage: float = Field(default=0, ge=0, le=100)
    score_explanation: NonEmptyText = (
        "evidence_score表示当前核验结论的启发式证据强度，不是文章真实性概率。"
    )
    evidence_source_assessments: list[EvidenceSourceAssessment] = Field(
        default_factory=list
    )
    credibility_assessment: CredibilityAssessment | None = None
    ai_explanation: VerificationAIExplanation | None = None
    display_result: VerificationDisplayResult | None = None
