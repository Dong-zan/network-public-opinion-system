from pydantic import BaseModel, Field


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


class Sentiment(BaseModel):
    positive: float | None = None
    neutral: float | None = None
    negative: float | None = None


class EventAnalysis(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    sentiment: Sentiment | None = None
    heat: float | None = None
    stage: str | None = None
    risk_level: str | None = None


class EventContext(BaseModel):
    event_id: int | str | None = None
    title: str = ""
    summary: str = ""
    update_time: str | None = None
    articles: list[Article] = Field(default_factory=list)
    analysis: EventAnalysis = Field(default_factory=EventAnalysis)
