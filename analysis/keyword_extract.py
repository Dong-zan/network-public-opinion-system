"""Keyword extraction for news text."""

from typing import List

from .dependencies import get_jieba_analyse
from .lexicon import load_sensitive_words


def _deduplicate(words: List[str]) -> List[str]:
    result = []
    seen = set()
    for word in words:
        normalized = word.strip()
        if len(normalized) < 2 or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _find_sensitive_hits(text: str) -> List[str]:
    sensitive_words = [word for word in load_sensitive_words() if len(word.strip()) >= 2 and word in text]
    return sorted(sensitive_words, key=lambda word: (text.find(word), -len(word)))


def extract_keywords(text: str, top_k: int = 5) -> List[str]:
    """Extract top keywords from news title and content."""
    if not text:
        return []

    candidate_count = max(top_k * 3, top_k)
    jieba_keywords = _deduplicate(
        get_jieba_analyse().extract_tags(text, topK=candidate_count, withWeight=False)
    )
    sensitive_hits = _find_sensitive_hits(text)

    selected = []
    for keyword in jieba_keywords:
        if any(sensitive in keyword for sensitive in sensitive_hits):
            selected.append(keyword)

    for sensitive in sensitive_hits:
        if not any(sensitive in keyword for keyword in selected):
            selected.append(sensitive)

    selected.extend(jieba_keywords)
    return _deduplicate(selected)[:top_k]
