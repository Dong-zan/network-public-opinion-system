from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field



class AIAsk(BaseModel):

    event_id:int=Field(
        gt=0
    )

    question:str=Field(
        min_length=1,
        max_length=2000
    )


class AIVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int = Field(gt=0)
    news_id: int = Field(gt=0)
    max_claims: int = Field(default=5, ge=1, le=10)


VerificationVerdict = Literal[
    "supported",
    "contradicted",
    "conflicting",
    "insufficient_evidence",
    "not_verifiable",
]


class AIVerifyClaimResult(BaseModel):
    """Critical claim fields required by the frontend and persistence layer."""

    model_config = ConfigDict(extra="allow")

    claim_id: int = Field(ge=1)
    claim: str = Field(min_length=1)
    verdict: VerificationVerdict
    independent_source_count: int = Field(ge=0)
    evidence: list[dict[str, Any]]
    context_evidence: list[dict[str, Any]]
    limitations: list[str]
    evidence_score: float | None = Field(ge=0, le=100)
    explanation: str | None


class AIVerifyDisplayResult(BaseModel):
    """Frontend-ready Verify fields. Extra future fields remain forwardable."""

    model_config = ConfigDict(extra="allow")

    headline: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    analysis_mode: Literal[
        "single_article_audit",
        "cross_source_verification",
    ] | None = None
    evidence_score_applicable: bool = True
    reasons: list[str]
    analysis_sections: list[dict[str, Any]] = Field(default_factory=list)
    claim_reviews: list[dict[str, Any]] = Field(default_factory=list)
    evidence_cards: list[dict[str, Any]]
    uncertainties: list[str]


class AIVerifyResult(BaseModel):
    """Normalized backend-to-frontend contract for POST /api/ai/verify."""

    model_config = ConfigDict(extra="allow")

    event_id: int = Field(gt=0)
    news_id: int = Field(gt=0)
    target_news_id: int = Field(gt=0)
    overall_verdict: VerificationVerdict
    evidence_score: float = Field(ge=0, le=100)
    score_type: Literal["heuristic_evidence_score"]
    claim_results: list[AIVerifyClaimResult]
    risk_flags: list[str]
    limitations: list[str]
    verifiable_claim_count: int = Field(ge=0)
    determinate_claim_count: int = Field(ge=0)
    verification_coverage: float = Field(ge=0, le=100)
    score_explanation: str = Field(min_length=1)
    evidence_source_assessments: list[dict[str, Any]]
    credibility_assessment: dict[str, Any] | None
    ai_explanation: dict[str, Any] | None
    display_result: AIVerifyDisplayResult | None


class AIVerifyAPIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[200]
    message: Literal["success"]
    data: AIVerifyResult
