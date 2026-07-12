from app.schemas.event import Article, EventContext
from app.services.evidence_retriever import EvidenceRetriever
from app.services.verification_service import VerificationService


def article(news_id, content: str, *, title: str = "报道", source: str = "媒体") -> Article:
    return Article(
        news_id=news_id,
        title=title,
        content=content,
        source=source,
        url=f"https://source-{news_id}.example/{news_id}",
    )


def long_report(fact: str) -> str:
    common = "这是关于同一事件的背景介绍，现场处置和信息核验工作持续进行。" * 30
    return common + fact + common


def test_high_similarity_with_different_number_is_not_deduplicated() -> None:
    target = article(1, "目标文章只用于选择。")
    first = article(2, long_report("事故造成3人受伤。"), source="媒体甲")
    second = article(3, long_report("事故造成5人受伤。"), source="媒体乙")

    selection = EvidenceRetriever(article_max_chars=5000).select_candidates(
        [target, first, second], target
    )

    assert [item.news_id for item in selection.articles] == [2, 3]
    assert selection.near_duplicate_fact_difference_count == 1


def test_high_similarity_with_different_location_is_not_deduplicated() -> None:
    target = article(1, "目标文章只用于选择。")
    first = article(2, long_report("事故发生在北京。"), source="媒体甲")
    second = article(3, long_report("事故发生在上海。"), source="媒体乙")

    selection = EvidenceRetriever(article_max_chars=5000).select_candidates(
        [target, first, second], target
    )

    assert len(selection.articles) == 2
    assert selection.near_duplicate_fact_difference_count == 1


def test_identical_body_still_deduplicates_with_different_metadata() -> None:
    target = article(1, "目标文章只用于选择。")
    body = long_report("事故造成3人受伤。")
    first = article(2, body, title="标题甲", source="媒体甲")
    second = article(3, body, title="标题乙", source="媒体乙")

    selection = EvidenceRetriever(article_max_chars=5000).select_candidates(
        [target, first, second], target
    )

    assert [item.news_id for item in selection.articles] == [2]
    assert selection.duplicate_count == 1


def test_service_flags_near_duplicate_with_fact_difference() -> None:
    target = article(1, "事故造成3人受伤。", source="目标媒体")
    first = article(2, long_report("事故造成3人受伤。"), source="媒体甲")
    second = article(3, long_report("事故造成5人受伤。"), source="媒体乙")

    response = VerificationService().verify(
        EventContext(articles=[target, first, second]),
        1,
    )

    assert "near_duplicate_with_fact_difference" in response.risk_flags
