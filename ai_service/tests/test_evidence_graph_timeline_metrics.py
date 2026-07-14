from app.schemas.event import Article, EventContext
from app.services.evidence_graph_service import EvidenceGraphService


def article(
    news_id: int,
    content: str,
    *,
    source: str | None = None,
    publish_time: str | None = "2026-07-08 09:00:00",
) -> Article:
    return Article(
        news_id=news_id,
        title=f"报道{news_id}",
        content=content,
        source=source or f"媒体{news_id}",
        url=f"https://source-{news_id}.example/{news_id}",
        publish_time=publish_time,
    )


def test_timeline_prefers_reference_time_then_event_time_then_publish_time() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "截至12时事故造成3人受伤。"),
                article(2, "事故发生于2026年7月8日10时。"),
                article(3, "事故发生在北京。", publish_time="2026-07-08 08:00:00"),
            ]
        )
    )
    sources = {entry.claim_type: entry.time_source for entry in response.timeline}

    assert sources["casualty"] == "reference_time"
    assert sources["event_time"] == "event_time"
    assert sources["location"] == "publish_time"


def test_publish_time_is_explicitly_labeled_and_not_event_time() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故发生在北京。", publish_time="2026-07-08 08:00:00")
            ]
        )
    )

    assert response.timeline[0].time_source == "publish_time"
    assert response.timeline[0].time.startswith("2026-07-08T08:00")


def test_update_edge_direction_follows_event_evolution() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "10时救援工作已经展开。", publish_time="2026-07-08 12:00:00"),
                article(2, "12时救援工作已经结束。", publish_time="2026-07-08 10:00:00"),
            ]
        )
    )
    update = next(edge for edge in response.edges if edge.edge_type == "updates")
    timeline = {entry.claim_node_id: entry for entry in response.timeline}

    assert timeline[update.source_node_id].time == "10:00"
    assert timeline[update.target_node_id].time == "12:00"
    assert "evolving_information" in response.risk_flags


def test_structural_metrics_are_explainable_ratios() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。"),
                article(2, "事故造成5人受伤。"),
            ]
        )
    )

    assert response.metrics.contradiction_edge_count == 1
    assert response.metrics.conflict_ratio == 1.0
    assert 0 <= response.metrics.reprint_ratio <= 1
    assert 0 <= response.metrics.unresolved_claim_ratio <= 1


def test_limits_are_deterministic_and_reported() -> None:
    event = EventContext(
        articles=[
            article(1, "事故造成3人受伤。事故发生在北京。" + "补充" * 30),
            article(2, "事故造成5人受伤。事故发生在上海。"),
            article(3, "救援工作已经展开。"),
        ]
    )
    service = EvidenceGraphService(
        max_articles=2,
        max_claims_per_article=1,
        max_edges=3,
        article_max_chars=30,
    )

    first = service.build(event)
    second = service.build(event)

    assert first == second
    assert first.metrics.article_count == 2
    assert len(first.edges) == first.metrics.returned_edge_count
    assert all(
        any(
            edge.edge_type == "asserts" and edge.target_node_id == node.node_id
            for edge in first.edges
        )
        for node in first.nodes
        if node.node_type == "claim"
    )
    assert "evidence_graph_input_truncated" in first.risk_flags
    assert any("文章数量" in item for item in first.limitations)
    assert any("主张数量" in item for item in first.limitations)
    assert any("正文超过" in item for item in first.limitations)


def test_missing_news_id_keeps_nodes_but_skips_relation_validation() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                Article(content="事故造成3人受伤。", source="媒体甲"),
                article(2, "事故造成3人受伤。"),
            ]
        )
    )

    assert response.metrics.article_count == 2
    assert "missing_article_identifiers" in response.risk_flags
    assert not any(
        edge.edge_type in {"supports", "contradicts", "updates"}
        for edge in response.edges
    )
