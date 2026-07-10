"""Keyword extraction for news text."""

from collections import Counter
from typing import List

from .preprocess import DOMAIN_WORDS, tokenize

try:
    import jieba.analyse
except ImportError:  # pragma: no cover - optional dependency fallback
    jieba = None


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

    if jieba:
        keywords = jieba.analyse.extract_tags(text, topK=top_k, withWeight=False)
        return [word for word in keywords if len(word.strip()) >= 2]

    tokens = tokenize(text)
    counter = Counter(tokens)
    for word in DOMAIN_WORDS:
        if word in text:
            counter[word] += 1
    for token in tokens:
        if token in SENSITIVE_WORDS:
            counter[token] += 2
    return [word for word, _ in counter.most_common(top_k)]
