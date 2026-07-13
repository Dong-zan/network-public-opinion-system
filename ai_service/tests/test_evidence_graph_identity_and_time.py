import pytest
from pydantic import ValidationError

from app.schemas.evidence_graph import EvidenceGraphRequest
from app.schemas.event import Article, EventContext
from app.services.evidence_graph_service import EvidenceGraphService
from app.services.evidence_retriever import EvidenceRetriever


def article(
    news_id: int | str | None,
    content: str,
    *,
    source: str = "",
    url: str = "",
    publish_time: str | None = "2026-07-08 10:00:00",
    title: str = "",
) -> Article:
    return Article(
        news_id=news_id,
        title=title,
        content=content,
        source=source,
        url=url,
        publish_time=publish_time,
    )


def article_nodes(response):
    return [node for node in response.nodes if node.node_type == "article"]


def relation_edges(response, edge_type: str):
    return [edge for edge in response.edges if edge.edge_type == edge_type]


def test_blank_news_ids_are_missing_not_the_same_identifier() -> None:
    retriever = EvidenceRetriever()
    assert retriever._same_news_id("", "   ") is False

    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article("", "事故造成3人受伤。"),
                article("   ", "事故造成5人受伤。"),
            ]
        )
    )

    assert "missing_article_identifiers" in response.risk_flags
    assert not relation_edges(response, "duplicates")


def test_nonempty_duplicate_news_ids_keep_existing_validation() -> None:
    with pytest.raises(ValidationError, match="证据图事件中的非空news_id必须唯一"):
        EvidenceGraphRequest(
            event=EventContext(
                articles=[
                    article(1, "事故造成3人受伤。"),
                    article("1", "事故造成5人受伤。"),
                ]
            )
        )


def test_anonymous_article_nodes_are_unique_and_all_edges_resolve() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(None, "事故造成3人受伤。"),
                article(None, "事故发生在北京。"),
            ]
        )
    )

    node_ids = [node.node_id for node in response.nodes]
    assert len(node_ids) == len(set(node_ids))
    assert len(article_nodes(response)) == 2
    assert all(
        edge.source_node_id in node_ids and edge.target_node_id in node_ids
        for edge in response.edges
    )


def test_identical_anonymous_articles_have_distinct_nodes_and_no_duplicate_self_loop() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(None, "事故造成3人受伤。"),
                article(None, "事故造成3人受伤。"),
            ]
        )
    )

    assert len({node.node_id for node in article_nodes(response)}) == 2
    duplicates = relation_edges(response, "duplicates")
    assert len(duplicates) == 1
    assert duplicates[0].source_node_id != duplicates[0].target_node_id


def test_same_url_with_different_facts_is_not_a_duplicate_for_anonymous_articles() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(None, "事故造成3人受伤。", url="https://example.com/report"),
                article(None, "事故造成5人受伤。", url="https://example.com/report"),
            ]
        )
    )

    assert len({node.node_id for node in article_nodes(response)}) == 2
    assert not relation_edges(response, "duplicates")
    assert "same_url_with_fact_difference" in response.risk_flags


def test_unknown_sources_do_not_create_independent_conflict() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。"),
                article(2, "事故造成5人受伤。"),
            ]
        )
    )

    contradiction = relation_edges(response, "contradicts")[0]
    assert contradiction.attributes["independent_sources"] is False
    assert contradiction.attributes["source_independence_known"] is False
    assert response.metrics.independent_source_count == 0
    assert all(cluster.status != "conflicting" for cluster in response.claim_clusters)
    assert "source_independence_unknown" in response.risk_flags


def test_known_different_sources_remain_independent() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", source="媒体甲", url="https://a.example/1"),
                article(2, "另一报道提到3人受伤。", source="媒体乙", url="https://b.example/2"),
            ]
        )
    )

    support = relation_edges(response, "supports")[0]
    assert support.attributes["independent_sources"] is True
    assert support.attributes["source_independence_known"] is True


def test_one_known_and_one_unknown_source_are_not_independent() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", source="媒体甲", url="https://a.example/1"),
                article(2, "另一报道提到3人受伤。"),
            ]
        )
    )

    support = relation_edges(response, "supports")[0]
    assert support.attributes["independent_sources"] is False
    assert support.attributes["source_independence_known"] is False


def test_same_known_source_is_not_independent() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", source="同一媒体", url="https://a.example/1"),
                article(2, "另一报道提到3人受伤。", source="同一媒体", url="https://b.example/2"),
            ]
        )
    )

    support = relation_edges(response, "supports")[0]
    assert support.attributes["independent_sources"] is False
    assert support.attributes["source_independence_known"] is True


def test_same_hostname_is_not_independent() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", source="媒体甲", url="https://same.example/1"),
                article(2, "另一报道提到3人受伤。", source="媒体乙", url="https://same.example/2"),
            ]
        )
    )

    support = relation_edges(response, "supports")[0]
    assert support.attributes["independent_sources"] is False
    assert support.attributes["source_independence_known"] is True


def test_month_day_time_infers_nearest_cross_year_date() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(
                    1,
                    "12月31日23时救援工作已经展开。",
                    source="媒体甲",
                    url="https://a.example/1",
                    publish_time="2027-01-01 00:30:00",
                ),
                article(
                    2,
                    "1月1日1时救援工作已经结束。",
                    source="媒体乙",
                    url="https://b.example/2",
                    publish_time="2027-01-01 01:30:00",
                ),
            ]
        )
    )
    timeline = {entry.summary: entry for entry in response.timeline}
    update = relation_edges(response, "updates")[0]

    assert timeline["12月31日23时救援工作已经展开"].year_inferred is True
    assert timeline["12月31日23时救援工作已经展开"].normalized_time.startswith("2026-12-31T23:00")
    assert timeline["1月1日1时救援工作已经结束"].normalized_time.startswith("2027-01-01T01:00")
    assert update.source_node_id == timeline["12月31日23时救援工作已经展开"].claim_node_id
    assert update.target_node_id == timeline["1月1日1时救援工作已经结束"].claim_node_id


def test_far_month_day_does_not_fabricate_a_year() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(
                    1,
                    "7月1日10时救援工作已经展开。",
                    source="媒体甲",
                    url="https://a.example/1",
                    publish_time="2027-01-01 00:00:00",
                )
            ]
        )
    )
    entry = next(item for item in response.timeline if item.claim_type == "response_status")

    assert entry.year_inferred is False
    assert entry.normalized_time is None


def test_cross_year_update_is_stable_when_article_input_is_reordered() -> None:
    early = article(
        1,
        "12月31日23时救援工作已经展开。",
        source="媒体甲",
        url="https://a.example/1",
        publish_time="2027-01-01 00:30:00",
    )
    late = article(
        2,
        "1月1日1时救援工作已经结束。",
        source="媒体乙",
        url="https://b.example/2",
        publish_time="2027-01-01 01:30:00",
    )

    first = relation_edges(
        EvidenceGraphService().build(EventContext(articles=[early, late])),
        "updates",
    )
    second = relation_edges(
        EvidenceGraphService().build(EventContext(articles=[late, early])),
        "updates",
    )

    assert first == second
