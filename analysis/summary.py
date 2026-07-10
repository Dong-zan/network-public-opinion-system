"""Event summary generation for backend storage and AI report context."""

import re
from typing import Dict, List

from .preprocess import clean_text, normalize_publish_time, normalize_source


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


def generate_summary(
    news: Dict,
    keywords: List[str] | None = None,
    max_length: int = 120,
) -> str:
    """
    Generate a concise event summary for one news item.

    The summary is intentionally rule-based so the backend can use it without
    requiring an external large-model service. It combines title, source,
    publish time, first content sentence and key terms.
    """
    title = clean_text(news.get("title", "")).strip(" ，。,.")
    content = clean_text(news.get("content", ""))
    source = normalize_source(news.get("source", ""))
    publish_time = normalize_publish_time(news.get("publish_time", ""))
    keywords = [word for word in (keywords or []) if word]

    sentences = _split_sentences(content)
    main_sentence = sentences[0] if sentences else ""

    parts = []
    if publish_time:
        parts.append(f"{publish_time}")
    source_phrase = _source_phrase(source)
    if source_phrase:
        parts.append(source_phrase)
    if title:
        parts.append(title)
    if main_sentence and main_sentence not in title:
        parts.append(main_sentence)

    summary = "，".join(parts)
    if keywords:
        summary = f"{summary}。关键词：{'、'.join(keywords[:5])}" if summary else f"关键词：{'、'.join(keywords[:5])}"

    return _trim_text(summary or "暂无摘要", max_length)
