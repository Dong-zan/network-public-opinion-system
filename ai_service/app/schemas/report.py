from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.event import EventContext


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _stable_unique_strings(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        normalized = item.strip() if isinstance(item, str) else item
        if normalized not in result:
            result.append(normalized)
    return result


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventContext


class EventOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: NonEmptyText | None = None
    location: NonEmptyText | None = None
    cause: NonEmptyText | None = None
    persons: list[NonEmptyText] = Field(default_factory=list)
    summary: NonEmptyText

    @field_validator("persons", mode="before")
    @classmethod
    def normalize_persons(cls, value: Any) -> Any:
        return _stable_unique_strings(value)


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overview: EventOverview
    summary: NonEmptyText
    trend_analysis: NonEmptyText
    risk_analysis: NonEmptyText
    suggestions: list[NonEmptyText] = Field(min_length=2, max_length=5)
    limitations: list[NonEmptyText] = Field(default_factory=list)

    @field_validator("suggestions", "limitations", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> Any:
        return _stable_unique_strings(value)
