"""Assign analyzed news articles to events by embedding similarity."""

from __future__ import annotations

from datetime import datetime
from math import sqrt
from typing import Iterable

from sqlalchemy.orm import Session

from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.services.embedding_utils import merge_embedding_center


EVENT_SIMILARITY_THRESHOLD = 0.75


def cosine_similarity(vector_a: Iterable[float], vector_b: Iterable[float]) -> float:
    """Calculate cosine similarity for two numeric vectors."""
    try:
        values_a = [float(value) for value in vector_a]
        values_b = [float(value) for value in vector_b]
    except (TypeError, ValueError):
        return 0.0

    if not values_a or len(values_a) != len(values_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(values_a, values_b))
    norm_a = sqrt(sum(value * value for value in values_a))
    norm_b = sqrt(sum(value * value for value in values_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class AggregationService:
    def __init__(self, db: Session):
        self.db = db

    def aggregate_article(self, news_id: int):
        print("========== 开始事件聚合 ==========")
        print("news_id:", news_id)

        article = self.db.query(Article).filter(
            Article.news_id == news_id
        ).first()
        if not article:
            print("没有找到文章:", news_id)
            return None

        analysis = self.db.query(Analysis).filter(
            Analysis.news_id == news_id
        ).first()
        if not analysis:
            print("没有找到分析结果")
            return None

        event, similarity = self._find_most_similar_event(analysis.embedding)

        if event is not None and similarity >= EVENT_SIMILARITY_THRESHOLD:
            print("复用已有事件:", event.event_id, "similarity:", similarity)
            self._update_event_embedding(event, analysis.embedding)
        else:
            event = self._create_event(article, analysis)
            print("创建新事件:", event.event_id, "best_similarity:", similarity)

        article.event_id = event.event_id
        analysis.event_id = event.event_id
        self.db.commit()

        print("文章绑定event完成")
        print("article.news_id:", article.news_id)
        print("event_id:", event.event_id)
        print("========== 事件聚合完成 ==========")
        return event

    def _find_most_similar_event(
        self,
        news_embedding: list[float] | None,
    ) -> tuple[Event | None, float]:
        if not news_embedding:
            return None, 0.0

        best_event = None
        best_similarity = 0.0

        events = self.db.query(Event).filter(
            Event.embedding.isnot(None)
        ).all()

        for event in events:
            similarity = cosine_similarity(news_embedding, event.embedding)
            if similarity > best_similarity:
                best_event = event
                best_similarity = similarity

        return best_event, best_similarity

    def _create_event(self, article: Article, analysis: Analysis) -> Event:
        event = Event(
            title=article.title,
            summary=article.content[:200] if article.content else "",
            heat=analysis.heat_score if analysis.heat_score else 0,
            risk_level=analysis.risk_level,
            stage=analysis.stage,
            embedding=analysis.embedding,
            embedding_count=1,
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    @staticmethod
    def _update_event_embedding(
        event: Event,
        new_embedding: list[float],
    ) -> None:
        old_count = event.embedding_count or 1
        event.embedding = merge_embedding_center(
            event.embedding,
            old_count,
            new_embedding,
        )
        event.embedding_count = old_count + 1
        event.update_time = datetime.now()
