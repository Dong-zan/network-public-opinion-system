from typing import Any

from pydantic import BaseModel, Field, field_validator


class Article(BaseModel):
    news_id: int | str | None = None
    title: str = ""
    content: str = ""
    source: str = ""
    url: str = ""
    publish_time: str | None = None
    platform: str = ""
    is_official: bool | None = None
    account_type: str | None = None
    source_type: str | None = None
    author: str | None = None
    reference_urls: list[str] = Field(default_factory=list)
    quoted_news_ids: list[int | str] = Field(default_factory=list)
    duplicate_group_id: str | None = None


class Sentiment(BaseModel):
    positive: float | None = None
    neutral: float | None = None
    negative: float | None = None


class AnalysisHistoryPoint(BaseModel):
    time: str | None = None
    heat: float | None = None
    article_count: int | None = None
    positive: float | None = None
    neutral: float | None = None
    negative: float | None = None


class EventAnalysis(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    sentiment: Sentiment | None = None
    heat: float | None = None
    stage: str | None = None
    risk_level: str | None = None
    history: list[AnalysisHistoryPoint] = Field(default_factory=list)

    @field_validator("history", mode="before")
    @classmethod
    def normalize_empty_history(cls, value: Any) -> Any:
        return [] if value is None else value


class EventContext(BaseModel):
    event_id: int | str | None = None
    title: str = ""
    summary: str = ""
    update_time: str | None = None
    articles: list[Article] = Field(default_factory=list)
    analysis: EventAnalysis = Field(default_factory=EventAnalysis)
