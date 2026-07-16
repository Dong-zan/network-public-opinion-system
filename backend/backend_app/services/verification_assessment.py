"""Derive user-facing authenticity and evidence-completeness metrics."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
from urllib.parse import urlparse


AUTHENTICITY_LABELS = {
    "high": "高",
    "medium": "中",
    "suspicious": "存疑",
    "low": "低",
}
COMPLETENESS_LABELS = {
    "complete": "完整",
    "general": "一般",
    "insufficient": "不足",
}


def enrich_verification_result(result: dict, context: dict) -> dict:
    """Add dual metrics without changing legacy verification fields."""
    normalized_result = dict(result or {})
    event = context.get("event", {}) if isinstance(context, dict) else {}
    articles = event.get("articles", []) if isinstance(event, dict) else []
    articles = [item for item in articles if isinstance(item, dict)]

    source_statistics, unique_source_count = _source_statistics(articles)
    source_type_count = len(source_statistics)
    time_consistency = _time_consistency(articles)
    subject_consistency = _subject_consistency(event, articles)
    consistency = _evidence_consistency(normalized_result)
    metadata_coverage = _metadata_coverage(articles)
    verification_coverage = _number(normalized_result.get("verification_coverage"))

    completeness_score = min(unique_source_count, 5) * 12
    completeness_score += min(source_type_count, 3) * 10
    completeness_score += round(metadata_coverage * 0.1)
    completeness_score += round(min(verification_coverage, 100) * 0.1)
    completeness_score = min(100, completeness_score)
    if completeness_score >= 75 and source_type_count >= 2:
        completeness_level = "complete"
    elif completeness_score >= 40:
        completeness_level = "general"
    else:
        completeness_level = "insufficient"

    category_counts = {
        item["type"]: item["count"]
        for item in source_statistics
    }
    official_confirmation = bool(category_counts.get("official", 0)) and (
        consistency == "consistent"
    )
    subject_mismatch = (
        bool(articles)
        and _has_subject_reference(event)
        and subject_consistency < 0.5
    )
    authenticity_level, authenticity_score = _authenticity_rating(
        source_count=unique_source_count,
        consistency=consistency,
        official_confirmation=official_confirmation,
        time_inconsistent=time_consistency == "inconsistent",
        subject_inconsistent=subject_mismatch,
    )

    authenticity_explanation = _authenticity_explanation(
        authenticity_level,
        consistency,
        unique_source_count,
        official_confirmation,
        time_consistency == "inconsistent",
        subject_mismatch,
    )
    completeness_explanation = _completeness_explanation(
        completeness_level,
        unique_source_count,
        source_type_count,
    )

    normalized_result["authenticity_assessment"] = {
        "level": authenticity_level,
        "label": AUTHENTICITY_LABELS[authenticity_level],
        "score": authenticity_score,
        "explanation": authenticity_explanation,
        "factors": {
            "source_count": unique_source_count,
            "source_type_count": source_type_count,
            "official_count": category_counts.get("official", 0),
            "news_media_count": category_counts.get("news_media", 0),
            "multi_source_consistency": consistency,
            "time_consistency": time_consistency,
            "subject_consistency": round(subject_consistency, 3),
            "source_conflict": consistency == "conflicting",
        },
    }
    normalized_result["evidence_completeness"] = {
        "level": completeness_level,
        "label": COMPLETENESS_LABELS[completeness_level],
        "score": completeness_score,
        "explanation": completeness_explanation,
        "source_count": unique_source_count,
        "source_type_count": source_type_count,
    }
    normalized_result["source_statistics"] = source_statistics
    return normalized_result


def _source_statistics(articles: list[dict]) -> tuple[list[dict], int]:
    counts = Counter()
    identities = set()
    for article in articles:
        category = _source_category(article)
        counts[category] += 1
        identities.add(_source_identity(article))

    labels = {
        "weibo": "微博",
        "news_media": "新闻媒体",
        "official": "官方机构",
        "other": "其他来源",
    }
    order = ("weibo", "news_media", "official", "other")
    statistics = [
        {"type": key, "label": labels[key], "count": counts[key]}
        for key in order
        if counts[key]
    ]
    return statistics, len(identities)


def _source_category(article: dict) -> str:
    source = str(article.get("source") or "").casefold()
    platform = str(article.get("platform") or "").casefold()
    account_type = str(article.get("account_type") or "").casefold()
    source_type = str(article.get("source_type") or "").casefold()
    if article.get("is_official") or any(
        marker in account_type or marker in source_type
        for marker in ("官方", "政府", "政务", "机构", "government")
    ):
        return "official"
    if "微博" in source or "微博" in platform or "weibo" in platform:
        return "weibo"
    if any(
        marker in account_type or marker in source_type or marker in platform
        for marker in ("媒体", "新闻", "media")
    ):
        return "news_media"
    return "other"


def _source_identity(article: dict) -> str:
    for key in ("account_id", "account_name", "author", "source"):
        value = str(article.get(key) or "").strip().casefold()
        if value:
            return f"{key}:{value}"
    hostname = urlparse(str(article.get("url") or "")).hostname
    if hostname:
        return f"host:{hostname.casefold()}"
    return f"news:{article.get('news_id', id(article))}"


def _evidence_consistency(result: dict) -> str:
    verdict = str(result.get("overall_verdict") or "").casefold()
    if verdict == "contradicted":
        return "contradicted"

    risk_flags = {
        str(item).strip().casefold()
        for item in (result.get("risk_flags") or [])
    }
    if verdict == "conflicting" or risk_flags & {
        "conflicting_evidence",
        "conflicting_claims_present",
        "same_source_internal_inconsistency",
        "same_url_with_fact_difference",
        "near_duplicate_with_fact_difference",
    }:
        return "conflicting"
    if verdict == "supported":
        return "consistent"

    stances = []
    for claim in result.get("claim_results") or []:
        for evidence in claim.get("evidence") or []:
            stances.append(str(evidence.get("stance") or "").casefold())
    if "supports" in stances and "contradicts" in stances:
        return "conflicting"
    if "contradicts" in stances:
        return "contradicted"
    if "supports" in stances:
        return "consistent"
    return "undetermined"


def _authenticity_rating(
    *,
    source_count: int,
    consistency: str,
    official_confirmation: bool,
    time_inconsistent: bool,
    subject_inconsistent: bool,
) -> tuple[str, int]:
    """Rate current credibility independently from evidence completeness."""
    if consistency == "contradicted":
        return "low", 20
    if consistency == "conflicting" or time_inconsistent or subject_inconsistent:
        return "suspicious", 45
    if official_confirmation:
        return "high", 90
    if source_count >= 3:
        return "high", 80 if consistency == "undetermined" else 85
    return "medium", 60


def _time_consistency(articles: list[dict]) -> str:
    timestamps = []
    for article in articles:
        # Publication dates can legitimately span an event's whole public-opinion
        # lifecycle. Only compare explicit event-time fields as factual timestamps.
        value = str(
            article.get("event_time")
            or article.get("occurred_at")
            or article.get("incident_time")
            or ""
        ).strip()
        if not value:
            continue
        try:
            timestamps.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            continue
    if len(timestamps) < 2:
        return "unknown"
    try:
        span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600
    except TypeError:
        return "unknown"
    return "consistent" if span_hours <= 168 else "inconsistent"


def _subject_consistency(event: dict, articles: list[dict]) -> float:
    if not articles:
        return 0.0
    keywords = [
        str(item).strip().casefold()
        for item in ((event.get("analysis") or {}).get("keywords") or [])
        if len(str(item).strip()) >= 2
    ]
    event_title = str(event.get("title") or "").casefold()
    title_tokens = set(re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}", event_title))
    matched = 0
    for article in articles:
        text = " ".join(
            str(article.get(key) or "").casefold()
            for key in ("title", "content")
        )
        if keywords and any(keyword in text for keyword in keywords):
            matched += 1
        elif title_tokens and any(token in text for token in title_tokens):
            matched += 1
    return matched / len(articles)


def _has_subject_reference(event: dict) -> bool:
    analysis = event.get("analysis") or {}
    has_keywords = any(
        len(str(item).strip()) >= 2
        for item in (analysis.get("keywords") or [])
    )
    return has_keywords or bool(str(event.get("title") or "").strip())


def _metadata_coverage(articles: list[dict]) -> float:
    if not articles:
        return 0.0
    present = 0
    total = len(articles) * 3
    for article in articles:
        present += bool(str(article.get("source") or "").strip())
        present += bool(str(article.get("url") or "").strip())
        present += bool(str(article.get("publish_time") or "").strip())
    return present / total * 100


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _authenticity_explanation(
    level: str,
    consistency: str,
    source_count: int,
    official_confirmation: bool,
    time_inconsistent: bool,
    subject_inconsistent: bool,
) -> str:
    if consistency == "contradicted":
        return "现有材料包含明确辟谣或反事实证据，当前事件真实性评估为低。"
    if consistency == "conflicting":
        return "不同来源对事件核心信息存在冲突，当前真实性评估为存疑。"
    if time_inconsistent:
        return "相关信息的时间线存在明显不一致，当前真实性评估为存疑。"
    if subject_inconsistent:
        return "相关信息涉及的主体与当前事件不一致，当前真实性评估为存疑。"
    if official_confirmation:
        return "事件已获得官方信息确认，当前真实性评估为高。"
    if level == "high":
        return f"已有{source_count}个独立来源围绕同一事件形成一致讨论，当前可信度较高。"
    return "现有信息未发现明显矛盾，当前事件具备一定可信度。"


def _completeness_explanation(
    level: str,
    source_count: int,
    source_type_count: int,
) -> str:
    if level == "complete":
        return f"已覆盖{source_count}个来源、{source_type_count}类来源，交叉证据较完整。"
    if level == "general":
        return f"当前覆盖{source_count}个来源、{source_type_count}类来源，证据完整度一般。"
    return f"当前仅覆盖{source_count}个来源、{source_type_count}类来源，证据仍需补充。"
