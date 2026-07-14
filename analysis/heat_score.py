"""Heat score and risk level calculation."""

from math import log10
from typing import Dict, List

from .lexicon import load_sensitive_words


def _number(value: object) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _interaction_score(news: Dict | None) -> float:
    if not news:
        return 0.0
    reposts = _number(news.get("repost_count")) * 3
    comments = _number(news.get("comment_count")) * 2
    likes = _number(news.get("like_count"))
    total = reposts + comments + likes
    if total <= 0:
        return 0.0
    return min(log10(total + 1) / 4 * 100, 100)


def calculate_heat_score(
    keywords: List[str],
    sentiment: Dict[str, float],
    similar_news: List[int],
    news: Dict | None = None,
) -> int:
    """Calculate public-opinion heat score from 0 to 100."""
    similar_score = min(len(similar_news) * 25, 100)
    sensitive_words = load_sensitive_words()
    sensitive_hits = sum(1 for word in keywords if any(sensitive in word for sensitive in sensitive_words))
    keyword_score = min(sensitive_hits * 25, 100)
    positive = sentiment.get("positive", 0)
    negative = sentiment.get("negative", 0)
    dominant_emotion = max(positive, negative)
    secondary_emotion = min(positive, negative)
    sentiment_score = min(dominant_emotion * 100 + secondary_emotion * 40, 100)
    interaction_score = _interaction_score(news)

    heat_score = similar_score * 0.35 + keyword_score * 0.2 + sentiment_score * 0.25 + interaction_score * 0.2
    return int(round(max(0, min(heat_score, 100))))


def judge_risk_level(heat_score: int, sentiment: Dict[str, float]) -> str:
    """Judge risk level as low, medium or high."""
    negative = sentiment.get("negative", 0)
    if heat_score >= 75 or negative >= 0.6:
        return "高"
    if heat_score >= 45 or negative >= 0.35:
        return "中"
    return "低"
