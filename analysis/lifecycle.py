"""Public-opinion lifecycle stage prediction."""

from datetime import datetime
from typing import Dict, List

from .preprocess import get_effective_time, normalize_publish_time, normalize_source


def _parse_time(value: str) -> datetime | None:
    normalized = normalize_publish_time(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _related_news(current_news: Dict, all_news: List[Dict], similar_news: List[int]) -> List[Dict]:
    similar_ids = set(similar_news)
    current_id = current_news.get("news_id")
    return [
        item
        for item in all_news
        if item.get("news_id") == current_id or item.get("news_id") in similar_ids
    ]


def _time_span_hours(news_items: List[Dict]) -> float:
    times = [_parse_time(get_effective_time(item)) for item in news_items]
    times = [value for value in times if value is not None]
    if len(times) < 2:
        return 0.0
    return (max(times) - min(times)).total_seconds() / 3600


def _platform_count(news_items: List[Dict]) -> int:
    platforms = {
        normalize_source(item.get("source", ""))
        for item in news_items
        if normalize_source(item.get("source", ""))
    }
    return len(platforms)


def predict_lifecycle(
    current_news: Dict,
    all_news: List[Dict],
    heat_score: int,
    similar_news: List[int],
    previous_heat_score: int | None = None,
) -> str:
    """
    Predict lifecycle stage with heat, related reports, time span and platforms.

    This richer function keeps the old stage labels but uses source and
    publish_time information from the backend, matching the analysis plan.
    """
    related = _related_news(current_news, all_news, similar_news)
    similar_count = len(similar_news)
    span_hours = _time_span_hours(related)
    platform_count = _platform_count(related)

    if previous_heat_score is not None:
        heat_drop = previous_heat_score - heat_score
        if heat_drop >= 15 and (span_hours >= 24 or similar_count <= 1):
            return "衰退期"

    if heat_score >= 75 or similar_count >= 4 or (platform_count >= 3 and heat_score >= 60):
        return "高潮期"

    if heat_score >= 45 or similar_count >= 2 or (span_hours <= 24 and platform_count >= 2):
        return "成长期"

    return "萌芽期"
