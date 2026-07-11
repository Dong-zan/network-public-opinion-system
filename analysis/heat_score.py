"""Heat score and risk level calculation."""

from typing import Dict, List

from .keyword_extract import SENSITIVE_WORDS


def calculate_heat_score(keywords: List[str], sentiment: Dict[str, float], similar_news: List[int]) -> int:
    """Calculate public-opinion heat score from 0 to 100."""
    similar_score = min(len(similar_news) * 25, 100)
    sensitive_hits = sum(1 for word in keywords if any(sensitive in word for sensitive in SENSITIVE_WORDS))
    keyword_score = min(sensitive_hits * 25, 100)
    positive = sentiment.get("positive", 0)
    negative = sentiment.get("negative", 0)
    dominant_emotion = max(positive, negative)
    secondary_emotion = min(positive, negative)
    sentiment_score = min(dominant_emotion * 100 + secondary_emotion * 40, 100)

    heat_score = similar_score * 0.45 + keyword_score * 0.25 + sentiment_score * 0.3
    return int(round(max(0, min(heat_score, 100))))


def judge_risk_level(heat_score: int, sentiment: Dict[str, float]) -> str:
    """Judge risk level as low, medium or high."""
    negative = sentiment.get("negative", 0)
    if heat_score >= 75 or negative >= 0.6:
        return "高"
    if heat_score >= 45 or negative >= 0.35:
        return "中"
    return "低"
