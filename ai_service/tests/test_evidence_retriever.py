from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor
from app.services.evidence_retriever import EvidenceRetriever


def make_article(news_id, title: str, content: str, source: str) -> Article:
    return Article(
        news_id=news_id,
        title=title,
        content=content,
        source=source,
        url=f"https://example.com/{news_id}",
    )


def test_identical_body_with_different_titles_and_sources_is_one_cluster() -> None:
    target = make_article(1, "目标", "事故造成3人受伤。", "媒体甲")
    first = make_article(2, "标题甲", "现场消息称事故中有3人受伤。", "媒体乙")
    second = make_article(3, "完全不同标题", first.content, "媒体丙")

    selection = EvidenceRetriever().select_candidates([target, first, second], target)

    assert [article.news_id for article in selection.articles] == [2]
    assert selection.duplicate_count == 1


def test_high_relevance_support_is_selected_over_low_relevance_contradiction() -> None:
    target = make_article(1, "目标", "事故造成3人受伤。", "媒体甲")
    candidate = make_article(
        2,
        "证据",
        "事故造成3人受伤。另一起外地事件造成5人受伤。",
        "媒体乙",
    )
    claim = ClaimExtractor().extract(target, 1)[0]

    retrieval = EvidenceRetriever().retrieve(claim, (candidate,))

    assert len(retrieval.evidence) == 1
    assert retrieval.evidence[0].stance == "supports"
    assert retrieval.evidence[0].quote == "事故造成3人受伤。"


def test_candidate_and_sentence_limits_are_reported() -> None:
    target = make_article(1, "目标", "事故造成3人受伤。", "媒体甲")
    candidates = [
        make_article(index, f"证据{index}", "事故造成3人受伤。第二句。", f"媒体{index}")
        for index in range(2, 6)
    ]
    retriever = EvidenceRetriever(max_candidates=2, max_sentences_per_article=1)

    selection = retriever.select_candidates([target, *candidates], target)
    claim = ClaimExtractor().extract(target, 1)[0]
    retrieval = retriever.retrieve(claim, selection.articles)

    assert len(selection.articles) == 1
    assert selection.duplicate_count == 3
    assert retrieval.sentence_limit_applied is True
