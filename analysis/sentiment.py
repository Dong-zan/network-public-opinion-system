"""Sentiment analysis utilities."""

from typing import Dict

from .dependencies import get_snownlp_class


def _normalize_distribution(positive: float, neutral: float, negative: float) -> Dict[str, float]:
    total = positive + neutral + negative
    if total <= 0:
        return {"positive": 0.0, "neutral": 1.0, "negative": 0.0}

    result = {
        "positive": round(positive / total, 2),
        "neutral": round(neutral / total, 2),
        "negative": round(negative / total, 2),
    }
    diff = round(1.0 - sum(result.values()), 2)
    result["neutral"] = round(result["neutral"] + diff, 2)
    return result


def analyze_sentiment(text: str) -> Dict[str, float]:
    """Return positive, neutral and negative ratios for one news item."""
    if not text:
        return {"positive": 0.0, "neutral": 1.0, "negative": 0.0}

    score = get_snownlp_class()(text).sentiments
    if score > 0.6:
        return _normalize_distribution(score, 0.2, 1 - score)
    if score < 0.4:
        return _normalize_distribution(score, 0.2, 1 - score)
    return _normalize_distribution(0.25, 0.5, 0.25)
