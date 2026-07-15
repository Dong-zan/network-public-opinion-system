from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ExplanationStatus = Literal["success", "fallback"]
ExplanationMethod = Literal["llm", "deterministic_fallback"]
DisplayEvidenceStance = Literal[
    "supports",
    "contradicts",
    "related",
    "updates",
]


class ExplainedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: int | str
    source: str = ""
    quote: NonEmptyText
    explanation: NonEmptyText


class ClaimAIExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: int = Field(ge=1)
    claim: NonEmptyText
    conclusion: NonEmptyText
    explanation: NonEmptyText
    evidence: list[ExplainedEvidence] = Field(default_factory=list, max_length=20)


class ExplanationReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: NonEmptyText
    title: NonEmptyText
    explanation: NonEmptyText
    claim_ids: list[int] = Field(default_factory=list, max_length=10)
    evidence_refs: list[int | str] = Field(default_factory=list, max_length=20)


class VerificationScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_risk: float = Field(ge=0, le=100)
    evidence_weight: float = Field(ge=0, le=1)
    evidence_contribution: float = Field(ge=0, le=100)
    source_risk: float = Field(ge=0, le=100)
    source_weight: float = Field(ge=0, le=1)
    source_contribution: float = Field(ge=0, le=100)
    language_risk: float = Field(ge=0, le=100)
    language_weight: float = Field(ge=0, le=1)
    language_contribution: float = Field(ge=0, le=100)
    total_risk_score: float = Field(ge=0, le=100)


class VerificationAIExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExplanationStatus
    analysis_method: ExplanationMethod
    headline: NonEmptyText
    conclusion: NonEmptyText
    why: list[ExplanationReason] = Field(default_factory=list, max_length=12)
    claim_explanations: list[ClaimAIExplanation] = Field(default_factory=list, max_length=10)
    score_breakdown: VerificationScoreBreakdown
    score_explanation: NonEmptyText
    limitations: list[NonEmptyText] = Field(default_factory=list, max_length=12)


class VerificationExplanationLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: NonEmptyText
    conclusion: NonEmptyText
    why: list[ExplanationReason] = Field(default_factory=list, max_length=12)
    claim_explanations: list[ClaimAIExplanation] = Field(default_factory=list, max_length=10)
    score_explanation: NonEmptyText
    limitations: list[NonEmptyText] = Field(default_factory=list, max_length=12)


class VerificationEvidenceCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: int | str
    source: str = ""
    source_description: NonEmptyText
    quote: NonEmptyText
    stance: DisplayEvidenceStance
    explanation: NonEmptyText
    url: str = ""


class VerificationDisplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: NonEmptyText
    conclusion: NonEmptyText
    analysis_mode: Literal["single_article_audit", "cross_source_verification"]
    evidence_score_applicable: bool
    reasons: list[NonEmptyText] = Field(default_factory=list, max_length=12)
    analysis_sections: list[ExplanationReason] = Field(default_factory=list, max_length=12)
    claim_reviews: list[ClaimAIExplanation] = Field(default_factory=list, max_length=10)
    evidence_cards: list[VerificationEvidenceCard] = Field(
        default_factory=list,
        max_length=20,
    )
    uncertainties: list[NonEmptyText] = Field(default_factory=list, max_length=12)
