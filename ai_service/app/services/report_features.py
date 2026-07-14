import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.event import Article, EventContext


@dataclass(frozen=True)
class ChronologicalUpdate:
    news_id: int | str | None
    publish_time: str | None
    source: str
    focus: tuple[str, ...]
    states_no_final_conclusion: bool
    states_rescue_started: bool


@dataclass(frozen=True)
class ReportFeatures:
    article_count: int
    source_count: int
    platform_count: int
    report_start_time: str | None
    report_end_time: str | None
    report_span_minutes: int | None
    chronological_updates: tuple[ChronologicalUpdate, ...]
    dominant_sentiment: str | None
    negative_ratio: float | None
    heat: float | None
    stage: str | None
    risk_level: str | None
    keywords: tuple[str, ...]
    critical_information_gaps: tuple[str, ...]
    conflict_topics: tuple[str, ...]
    heat_history: tuple[tuple[datetime, float], ...]
    sentiment_history_count: int


def extract_report_features(
    event: EventContext,
    articles: list[Article],
) -> ReportFeatures:
    valid_articles = [article for article in articles if article.content.strip()]
    timed_articles = [
        (parsed, index, article)
        for index, article in enumerate(valid_articles)
        if (parsed := _parse_time(article.publish_time)) is not None
    ]
    timed_articles.sort(key=lambda item: (item[0], item[1]))
    untimed_articles = [
        article
        for article in valid_articles
        if _parse_time(article.publish_time) is None
    ]
    ordered_articles = [article for _, _, article in timed_articles] + untimed_articles

    chronological_updates = tuple(
        ChronologicalUpdate(
            news_id=article.news_id,
            publish_time=article.publish_time,
            source=article.source.strip(),
            focus=tuple(_article_focus(article.content)),
            states_no_final_conclusion=any(
                marker in article.content
                for marker in (
                    "尚无最终调查结论",
                    "暂无最终调查结论",
                    "最终调查结论尚未",
                )
            ),
            states_rescue_started=any(
                marker in article.content
                for marker in (
                    "救援工作已经展开",
                    "救援已经展开",
                    "救援工作已展开",
                    "救援已展开",
                )
            ),
        )
        for article in ordered_articles
    )

    start_time = timed_articles[0][2].publish_time if timed_articles else None
    end_time = timed_articles[-1][2].publish_time if timed_articles else None
    span_minutes = None
    if len(timed_articles) >= 2:
        span = timed_articles[-1][0] - timed_articles[0][0]
        span_minutes = max(int(span.total_seconds() // 60), 0)

    sentiment_values = {}
    if event.analysis.sentiment is not None:
        sentiment_values = {
            label: value
            for label, value in (
                ("正面", event.analysis.sentiment.positive),
                ("中性", event.analysis.sentiment.neutral),
                ("负面", event.analysis.sentiment.negative),
            )
            if value is not None
        }
    dominant_sentiment = (
        max(sentiment_values, key=sentiment_values.get) if sentiment_values else None
    )

    contents = [" ".join(article.content.split()) for article in valid_articles]
    return ReportFeatures(
        article_count=len(valid_articles),
        source_count=len({article.source.strip() for article in valid_articles if article.source.strip()}),
        platform_count=len(
            {article.platform.strip() for article in valid_articles if article.platform.strip()}
        ),
        report_start_time=start_time,
        report_end_time=end_time,
        report_span_minutes=span_minutes,
        chronological_updates=chronological_updates,
        dominant_sentiment=dominant_sentiment,
        negative_ratio=(
            event.analysis.sentiment.negative
            if event.analysis.sentiment is not None
            else None
        ),
        heat=event.analysis.heat,
        stage=event.analysis.stage,
        risk_level=event.analysis.risk_level,
        keywords=tuple(_stable_unique(event.analysis.keywords)),
        critical_information_gaps=tuple(_critical_information_gaps(contents)),
        conflict_topics=tuple(_conflict_topics(contents)),
        heat_history=tuple(_valid_heat_history(event)),
        sentiment_history_count=_valid_sentiment_history_count(event),
    )


def _article_focus(content: str) -> list[str]:
    categories = (
        ("现场处置", ("现场处置", "现场控制", "应急处置")),
        ("救援进展", ("救援", "搜救")),
        ("原因调查", ("原因", "事故原因")),
        ("伤亡情况", ("伤亡", "受伤", "死亡", "遇难")),
        ("最终调查结论", ("最终调查结论", "调查结论")),
        ("回应与通报", ("回应", "通报", "声明")),
    )
    result = [
        label
        for label, markers in categories
        if any(marker in content for marker in markers)
    ]
    return result or ["事件进展"]


def _critical_information_gaps(contents: list[str]) -> list[str]:
    text = " ".join(contents)
    gaps = []
    if any(marker in text for marker in ("原因仍在调查", "具体原因仍在调查", "具体原因仍在进一步调查", "原因尚在调查")):
        gaps.append("事件原因仍待调查")
    elif not any(marker in text for marker in ("原因是", "由于", "因", "初步排查显示", "初步原因", "有关")):
        gaps.append("事件原因尚未说明")

    location_pattern = r"(?:事发于|发生在|位于|发生地点为|事故地点为|事发地点为|事故地点是|事发地是|地点位于)\s*[\u4e00-\u9fff]{2,32}(?:省|市|区|县|镇|村|路|街道|机场|车站|学校|医院|产业园|园区|电站)"
    if not re.search(location_pattern, text):
        gaps.append("事件地点尚未明确")

    if not any(marker in text for marker in ("伤亡", "受伤", "死亡", "遇难")):
        gaps.append("伤亡情况尚未明确")

    if any(marker in text for marker in ("尚无最终调查结论", "暂无最终调查结论", "最终调查结论尚未")):
        gaps.append("最终调查结论尚未形成")
    elif "最终调查结论" not in text and "调查结论" not in text:
        gaps.append("最终调查结论尚未提供")

    person_patterns = (
        r"(?:负责人|记者|发言人|驾驶员|组织者)\s*[\u4e00-\u9fff]{2,4}(?=组织|表示|介绍|称|带领|负责|[，。；])",
        r"[\u4e00-\u9fff]{2,4}(?:组织|带领|表示|介绍|称|负责)",
    )
    if not any(re.search(pattern, text) for pattern in person_patterns):
        gaps.append("具体涉事人物或机构尚未明确")
    return _stable_unique(gaps)


def _conflict_topics(contents: list[str]) -> list[str]:
    text = " ".join(contents)
    topics = []
    if (
        any(marker in text for marker in ("救援已经展开", "救援工作已经展开", "正在救援"))
        and any(marker in text for marker in ("救援尚未展开", "未开展救援", "尚未救援"))
    ):
        topics.append("救援进展口径")

    casualty_values = set(re.findall(r"(?:伤亡|死亡|受伤|遇难)\D{0,4}(\d+)人", text))
    if len(casualty_values) > 1:
        topics.append("伤亡人数口径")

    if (
        any(marker in text for marker in ("已有最终调查结论", "最终调查结论已经公布"))
        and any(marker in text for marker in ("尚无最终调查结论", "暂无最终调查结论"))
    ):
        topics.append("最终调查结论口径")
    return topics


def _valid_heat_history(event: EventContext) -> list[tuple[datetime, float]]:
    points = []
    for index, item in enumerate(event.analysis.history):
        parsed = _parse_time(item.time)
        if parsed is None or item.heat is None:
            continue
        points.append((parsed, index, item.heat))
    points.sort(key=lambda item: (item[0], item[1]))
    return [(parsed, heat) for parsed, _, heat in points]


def _valid_sentiment_history_count(event: EventContext) -> int:
    return sum(
        _parse_time(item.time) is not None
        and any(
            value is not None
            for value in (item.positive, item.neutral, item.negative)
        )
        for item in event.analysis.history
    )


def _parse_time(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _stable_unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result
