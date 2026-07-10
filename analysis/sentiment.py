"""Sentiment analysis utilities."""

from typing import Dict

try:
    from snownlp import SnowNLP
except ImportError:  # pragma: no cover - optional dependency fallback
    SnowNLP = None


NEGATIVE_WORDS = {
    "事故",
    "伤亡",
    "死亡",
    "受伤",
    "火灾",
    "爆炸",
    "投诉",
    "处罚",
    "违法",
    "违规",
    "风险",
    "谣言",
    "恐慌",
    "质疑",
    "危机",
    "冲突",
}

POSITIVE_WORDS = {
    "救援",
    "辟谣",
    "澄清",
    "恢复",
    "表彰",
    "成功",
    "改善",
    "保障",
    "回应",
    "通报",
    "处置",
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


def analyze_sentiment(text: str) -> Dict[str, float]:
    """Return positive, neutral and negative ratios for one news item."""
    if not text:
        return {"positive": 0.0, "neutral": 1.0, "negative": 0.0}

    if SnowNLP:
        score = SnowNLP(text).sentiments
        if score > 0.6:
            return _normalize_distribution(score, 0.2, 1 - score)
        if score < 0.4:
            return _normalize_distribution(score, 0.2, 1 - score)
        return _normalize_distribution(0.25, 0.5, 0.25)

    negative_hits = sum(1 for word in NEGATIVE_WORDS if word in text)
    positive_hits = sum(1 for word in POSITIVE_WORDS if word in text)
    if negative_hits == 0 and positive_hits == 0:
        return {"positive": 0.2, "neutral": 0.6, "negative": 0.2}

    return _normalize_distribution(positive_hits + 1, 2, negative_hits + 1)
