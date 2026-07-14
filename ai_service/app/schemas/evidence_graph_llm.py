from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


LLMGraphNodeType = Literal["article", "claim", "evidence", "source"]
LLMGraphRelation = Literal[
    "contains",
    "supports",
    "contradicts",
    "adds_detail",
    "updates",
    "same_fact",
    "quotes",
    "reposts",
]


class EvidenceGraphLLMNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: LLMGraphNodeType
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    news_id: int | str | None = None
    source: str | None = None
    quote: str | None = None

    @field_validator("id", "label", "description")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("source", "quote")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EvidenceGraphLLMEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relation: LLMGraphRelation
    label: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    news_id: int | str | None = None
    quote: str | None = None
    confidence: float = Field(ge=0, le=1)

    @field_validator("id", "source", "target", "label", "explanation")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("quote")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EvidenceGraphLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    nodes: list[EvidenceGraphLLMNode] = Field(default_factory=list)
    edges: list[EvidenceGraphLLMEdge] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("summary must not be blank")
        return stripped

    @field_validator("key_findings", "limitations")
    @classmethod
    def clean_text_list(cls, values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result
