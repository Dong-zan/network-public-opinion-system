from pydantic import BaseModel, ConfigDict, Field

from app.schemas.verification import (
    ClaimSourceRoleAssessment,
    SemanticLanguageRiskFlag,
)


class SemanticLLMOutput(BaseModel):
    """Strict, score-free contract accepted from the semantic model."""

    model_config = ConfigDict(extra="forbid")

    language_flags: list[SemanticLanguageRiskFlag] = Field(default_factory=list, max_length=24)
    source_role_assessments: list[ClaimSourceRoleAssessment] = Field(default_factory=list, max_length=24)
