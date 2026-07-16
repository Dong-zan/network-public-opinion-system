from datetime import datetime

from pydantic import BaseModel


class SentimentDistribution(BaseModel):

    positive: float | None = None
    neutral: float | None = None
    negative: float | None = None


class NewsItem(BaseModel):

    news_id: int
    event_id: int | None = None
    title: str | None = None
    source: str | None = None
    publish_time: datetime | None = None
    summary: str
    content: str | None = None
    url: str | None = None
    heat: float | None = None
    risk_level: str | None = None
    stage: str | None = None
    platform: str | None = None
    sentiment_distribution: SentimentDistribution | None = None


class NewsListResponse(BaseModel):

    code: int
    message: str
    data: list[NewsItem]


class EventNewsItem(BaseModel):

    news_id: int
    event_id: int
    title: str | None = None
    source: str | None = None
    publish_time: datetime | None = None
    summary: str
    content: str | None = None
    url: str | None = None
    sentiment_distribution: SentimentDistribution | None = None


class EventNewsListResponse(BaseModel):

    code: int
    message: str
    data: list[EventNewsItem]
