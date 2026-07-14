"""Calculate and persist event-level heat from all articles in an event."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.models.event_heat_history import EventHeatHistory


class EventHeatService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_event_heat(self, event_id: int) -> float:
        articles = self.db.query(Article).filter(
            Article.event_id == event_id
        ).all()

        article_count = len(articles)
        volume_score = min(article_count * 10, 100)

        recent_cutoff = datetime.now() - timedelta(hours=24)
        recent_count = sum(
            1
            for article in articles
            if article.created_at is not None
            and article.created_at >= recent_cutoff
        )
        velocity_score = min(recent_count * 10, 100)

        news_ids = [article.news_id for article in articles]
        analyses = []
        if news_ids:
            analyses = self.db.query(Analysis).filter(
                Analysis.news_id.in_(news_ids)
            ).all()

        heat_values = [
            float(analysis.heat_score)
            for analysis in analyses
            if analysis.heat_score is not None
        ]
        if heat_values:
            average_heat = sum(heat_values) / len(heat_values)
            max_heat = max(heat_values)
            news_heat_score = 0.3 * average_heat + 0.7 * max_heat
        else:
            news_heat_score = 0.0

        negative_values = [
            float(analysis.negative)
            for analysis in analyses
            if analysis.negative is not None
        ]
        negative_avg = (
            sum(negative_values) / len(negative_values)
            if negative_values
            else 0.0
        )
        sentiment_score = negative_avg * 100

        event_heat = (
            0.35 * volume_score
            + 0.25 * velocity_score
            + 0.30 * news_heat_score
            + 0.10 * sentiment_score
        )
        return float(max(0.0, min(event_heat, 100.0)))

    def update_event_heat(self, event_id: int) -> float:
        event = self.db.query(Event).filter(
            Event.event_id == event_id
        ).first()
        if not event:
            return 0.0

        event_heat = self.calculate_event_heat(event_id)
        now = datetime.now()
        event.heat = event_heat
        event.update_time = now
        self.db.add(
            EventHeatHistory(
                event_id=event_id,
                heat=event_heat,
                created_at=now,
            )
        )
        self.db.commit()
        self.db.refresh(event)
        return event_heat
