"""Keyword extraction for news text."""

from typing import List

from .dependencies import get_jieba_analyse


SENSITIVE_WORDS = {
    "突发",
    "事故",
    "通报",
    "回应",
    "救援",
    "调查",
    "官方",
    "网传",
    "爆料",
    "舆情",
    "投诉",
    "处罚",
    "风险",
    "伤亡",
    "火灾",
    "安全",
}


def extract_keywords(text: str, top_k: int = 5) -> List[str]:
    """Extract top keywords from news title and content."""
    if not text:
        return []

    keywords = get_jieba_analyse().extract_tags(text, topK=top_k, withWeight=False)
    return [word for word in keywords if len(word.strip()) >= 2]
