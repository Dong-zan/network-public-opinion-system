"""Determine an event lifecycle stage from event-level heat history."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.models.event_heat_history import EventHeatHistory


class EventLifecycleService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_stage(self, event_id: int) -> str:
        event = self.db.query(Event).filter(
            Event.event_id == event_id
        ).first()
        if not event:
            return "萌芽期"

        current_heat = float(event.heat or 0)
        histories = self.db.query(EventHeatHistory).filter(
            EventHeatHistory.event_id == event_id
        ).order_by(
            EventHeatHistory.created_at.desc(),
            EventHeatHistory.id.desc(),
        ).limit(5).all()

        # Keep event-level activity available as lifecycle input. The first
        # version rules below are intentionally driven only by heat trends.
        self.db.query(Article).filter(
            Article.event_id == event_id
        ).count()
        recent_cutoff = datetime.now() - timedelta(hours=24)
        self.db.query(Article).filter(
            Article.event_id == event_id,
            Article.created_at >= recent_cutoff,
        ).count()

        chronological_heats = [
            float(history.heat)
            for history in reversed(histories)
        ]

        if len(chronological_heats) >= 3:
            latest_three = chronological_heats[-3:]
            if latest_three[0] > latest_three[1] > latest_three[2]:
                return "衰退期"

        if chronological_heats:
            recent_max = max(chronological_heats)
            if recent_max > 0 and current_heat < recent_max * 0.5:
                return "衰退期"

        if current_heat >= 70:
            return "高潮期"

        if len(chronological_heats) >= 2:
            recent_growth = (
                chronological_heats[-1] - chronological_heats[-2]
            )
            if recent_growth > 20:
                return "高潮期"

        if current_heat >= 30 and self._is_recently_rising(
            chronological_heats
        ):
            return "成长期"

        return "萌芽期"

    def update_stage(self, event_id: int) -> str:
        event = self.db.query(Event).filter(
            Event.event_id == event_id
        ).first()
        if not event:
            return "萌芽期"

        stage = self.calculate_stage(event_id)
        event.stage = stage
        event.update_time = datetime.now()
        self.db.commit()
        self.db.refresh(event)
        return stage

    @staticmethod
    def _is_recently_rising(heats: list[float]) -> bool:
        if len(heats) < 2:
            return False

        recent_heats = heats[-3:]
        return all(
            earlier < later
            for earlier, later in zip(recent_heats, recent_heats[1:])
        )
