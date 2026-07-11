"""Similar news discovery based on TF-IDF and cosine similarity."""

from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, List

from .dependencies import get_sklearn_similarity_tools
from .preprocess import merge_title_content, normalize_publish_time, normalize_source, normalize_url, tokenize


def _parse_time(value: str) -> datetime | None:
    normalized = normalize_publish_time(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _time_similarity(news_a: Dict, news_b: Dict) -> float:
    time_a = _parse_time(news_a.get("publish_time", ""))
    time_b = _parse_time(news_b.get("publish_time", ""))
    if not time_a or not time_b:
        return 0.0

    hours = abs((time_a - time_b).total_seconds()) / 3600
    if hours <= 6:
        return 1.0
    if hours <= 24:
        return 0.7
    if hours <= 72:
        return 0.4
    return 0.0


def _source_similarity(news_a: Dict, news_b: Dict) -> float:
    source_a = normalize_source(news_a.get("source", ""))
    source_b = normalize_source(news_b.get("source", ""))
    if not source_a or not source_b:
        return 0.0
    if source_a == source_b:
        return 1.0
    if source_a in source_b or source_b in source_a:
        return 0.5
    return 0.0


def _url_domain(url: str) -> str:
    value = normalize_url(url)
    if not value:
        return ""
    parsed = urlparse(value)
    return parsed.netloc.lower()


def _url_similarity(news_a: Dict, news_b: Dict) -> float:
    domain_a = _url_domain(news_a.get("url", ""))
    domain_b = _url_domain(news_b.get("url", ""))
    if not domain_a or not domain_b:
        return 0.0
    return 1.0 if domain_a == domain_b else 0.0


def _combine_similarity(text_score: float, current_news: Dict, candidate: Dict) -> float:
    """Combine text score with metadata that helps event aggregation."""
    # Metadata can strengthen a text match, but should not make unrelated news
    # items similar only because they were published close together.
    if text_score < 0.08:
        return text_score

    metadata_score = (
        _time_similarity(current_news, candidate) * 0.07
        + _source_similarity(current_news, candidate) * 0.04
        + _url_similarity(current_news, candidate) * 0.02
    )
    return min(1.0, text_score * 0.87 + metadata_score)


def find_similar_news(
    current_news: Dict,
    all_news: List[Dict],
    threshold: float = 0.18,
    max_count: int = 5,
) -> List[int]:
    """Find news IDs with high textual similarity to the current item."""
    current_id = current_news.get("news_id")
    candidates = [item for item in all_news if item.get("news_id") != current_id]
    if not candidates:
        return []

    texts = [merge_title_content(current_news)] + [merge_title_content(item) for item in candidates]
    TfidfVectorizer, cosine_similarity = get_sklearn_similarity_tools()
    vectorizer = TfidfVectorizer(tokenizer=tokenize, token_pattern=None)
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return []

    similarities = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    scored_items = [
        (item, _combine_similarity(float(score), current_news, item))
        for item, score in zip(candidates, similarities)
    ]

    similar = [
        (item.get("news_id"), score)
        for item, score in scored_items
        if item.get("news_id") is not None and score >= threshold
    ]
    similar.sort(key=lambda pair: pair[1], reverse=True)
    return [news_id for news_id, _ in similar[:max_count]]
