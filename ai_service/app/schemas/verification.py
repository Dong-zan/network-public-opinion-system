from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.event import EventContext


VerificationVerdict = Literal[
    "supported",
    "contradicted",
    "conflicting",
    "insufficient_evidence",
    "not_verifiable",
]
EvidenceStance = Literal["supports", "contradicts"]
ContextEvidenceRelation = Literal["related", "updates"]
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
            if article.news_id is None or not str(article.news_id).strip():
                continue
            key = str(article.news_id).strip()
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
