"""Sentiment analysis utilities."""

from typing import Dict

from .dependencies import get_snownlp_class
from .lexicon import load_sensitive_words


NEGATIVE_HINT_WORDS = {
    "事故",
    "突发",
    "火灾",
    "伤亡",
    "死亡",
    "自杀",
    "身亡",
    "遇难",
    "受伤",
    "失联",
    "中毒",
    "爆炸",
    "踩踏",
    "塌方",
    "台风",
    "暴雨",
    "洪水",
    "强降雨",
    "极端天气",
    "预警",
    "风险",
    "危机",
    "违法",
    "违规",
    "诈骗",
    "泄露",
    "隐患",
    "纠纷",
    "投诉",
}


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


def _risk_hint_count(text: str) -> int:
    words = set(load_sensitive_words()) | NEGATIVE_HINT_WORDS
    return sum(1 for word in words if word and word in text)


def _apply_public_opinion_correction(text: str, sentiment: Dict[str, float]) -> Dict[str, float]:
    hits = _risk_hint_count(text)
    if hits <= 0:
        return sentiment

    positive = sentiment.get("positive", 0.0)
    neutral = sentiment.get("neutral", 0.0)
    negative = sentiment.get("negative", 0.0)

    if hits >= 3:
        target_negative = 0.6
    elif hits == 2:
        target_negative = 0.5
    else:
        target_negative = 0.38

    if negative >= target_negative:
        return sentiment

    negative = target_negative
    positive = min(positive, max(0.1, 1.0 - negative - 0.2))
    neutral = max(0.0, 1.0 - positive - negative)
    return _normalize_distribution(positive, neutral, negative)


def analyze_sentiment(text: str) -> Dict[str, float]:
    """Return positive, neutral and negative ratios for one news item."""
    if not text:
        return {"positive": 0.0, "neutral": 1.0, "negative": 0.0}

    score = get_snownlp_class()(text).sentiments
    if score > 0.6:
        sentiment = _normalize_distribution(score, 0.2, 1 - score)
    elif score < 0.4:
        sentiment = _normalize_distribution(score, 0.2, 1 - score)
    else:
        sentiment = _normalize_distribution(0.25, 0.5, 0.25)
    return _apply_public_opinion_correction(text, sentiment)
