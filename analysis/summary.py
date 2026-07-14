"""Event summary generation for backend storage and AI report context."""

import re
from typing import Dict, List

from .lexicon import load_sensitive_words
from .preprocess import clean_text, normalize_publish_time, normalize_source, tokenize


def _split_sentences(text: str) -> List[str]:
    """Split Chinese news text into short candidate sentences."""
    cleaned = clean_text(text)
    if not cleaned:
        return []
    sentences = re.split(r"[。！？!?；;]", cleaned)
    return [sentence.strip(" ，。,.") for sentence in sentences if sentence.strip()]


def _trim_text(text: str, max_length: int) -> str:
    """Trim a summary to a display-friendly length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip("，。,. ") + "…"


def _source_phrase(source: str) -> str:
    """Build a natural source phrase for the summary."""
    if not source:
        return ""
    if source.endswith(("发布", "新闻", "平台", "频道", "客户端")):
        return source
    return f"{source}发布"


def _overlap_ratio(text_a: str, text_b: str) -> float:
    tokens_a = set(tokenize(text_a))
    tokens_b = set(tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _sentence_score(sentence: str, title: str, keywords: List[str]) -> float:
    tokens = tokenize(sentence)
    if not tokens:
        return 0.0

    keyword_hits = sum(1 for word in keywords if word and word in sentence)
    sensitive_hits = sum(1 for word in load_sensitive_words() if word in sentence)
    title_overlap = _overlap_ratio(sentence, title)
    length_score = min(len(sentence) / 60, 1.0)

    if title and sentence in title:
        title_overlap = 1.0

    duplicate_penalty = 0.45 if title_overlap >= 0.85 else 0.0
    return keyword_hits * 2.0 + sensitive_hits * 1.2 + title_overlap * 0.8 + length_score - duplicate_penalty


def _select_main_sentences(content: str, title: str, keywords: List[str], max_count: int = 2) -> List[str]:
    sentences = _split_sentences(content)
    if not sentences:
        return []

    scored = []
    for index, sentence in enumerate(sentences):
        if title and _overlap_ratio(sentence, title) >= 0.9:
            continue
        scored.append((_sentence_score(sentence, title, keywords), index, sentence))

    if not scored:
        return [sentences[0]]

    selected = sorted(scored, key=lambda item: (-item[0], item[1]))[:max_count]
    return [sentence for _, _, sentence in sorted(selected, key=lambda item: item[1])]


def _build_keyword_suffix(keywords: List[str]) -> str:
    if not keywords:
        return ""
    return f"关键词：{'、'.join(keywords[:5])}"


def generate_summary(
    news: Dict,
    keywords: List[str] | None = None,
    max_length: int = 120,
) -> str:
    """
    Generate a concise event summary for one news item.

    Candidate content sentences are ranked by keyword density, sensitive-word
    hits, title overlap and readable length.
    """
    title = clean_text(news.get("title", "")).strip(" ，。,.")
    content = clean_text(news.get("content", ""))
    source = normalize_source(news.get("source", ""))
    publish_time = normalize_publish_time(news.get("publish_time", ""))
    keywords = [word for word in (keywords or []) if word]

    parts = []
    if publish_time:
        parts.append(f"{publish_time}")
    source_phrase = _source_phrase(source)
    if source_phrase:
        parts.append(source_phrase)
    if title:
        parts.append(title)

    for sentence in _select_main_sentences(content, title, keywords):
        if sentence and sentence not in parts:
            parts.append(sentence)

    body = "，".join(parts)
    keyword_suffix = _build_keyword_suffix(keywords)
    if not body and not keyword_suffix:
        return "暂无摘要"
    if not keyword_suffix:
        return _trim_text(body, max_length)

    suffix = f"。{keyword_suffix}" if body else keyword_suffix
    body_budget = max_length - len(suffix)
    if body_budget <= 0:
        return _trim_text(keyword_suffix, max_length)

    trimmed_body = _trim_text(body, body_budget).rstrip("，。,. ")
    return f"{trimmed_body}{suffix}" if trimmed_body else keyword_suffix
