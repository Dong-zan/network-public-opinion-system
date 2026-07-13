from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.evidence_graph import EvidenceGraphRequest
from app.schemas.event import Article, EventContext
from app.services.evidence_graph_service import EvidenceGraphService


def article(
    news_id: int | str,
    content: str,
    source: str,
    *,
    url: str | None = None,
    publish_time: str = "2026-07-08 10:00:00",
) -> Article:
    return Article(
        news_id=news_id,
        title=f"报道{news_id}",
        content=content,
        source=source,
        url=url or f"https://source-{news_id}.example/{news_id}",
        publish_time=publish_time,
    )


def relation_edge(response, edge_type: str):
    return next(edge for edge in response.edges if edge.edge_type == edge_type)


def cluster_by_type(response, claim_type: str):
    return [cluster for cluster in response.claim_clusters if cluster.claim_type == claim_type]


def test_duplicate_nonempty_news_id_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError, match="证据图事件中的非空news_id必须唯一"):
        EvidenceGraphRequest(
            event=EventContext(
                articles=[
                    article(1, "事故造成3人受伤。", "媒体甲"),
                    article("1", "事故造成5人受伤。", "媒体乙"),
                ]
            )
        )


def test_duplicate_nonempty_news_id_returns_422(client, event_payload) -> None:
    event = deepcopy(event_payload)
    event["articles"] = [
        article(1, "事故造成3人受伤。", "媒体甲").model_dump(),
        article("1", "事故造成5人受伤。", "媒体乙").model_dump(),
    ]

    response = client.post("/ai/evidence-graph", json={"event": event})

    assert response.status_code == 422
    assert "证据图事件中的非空news_id必须唯一" in str(response.json())


def test_asserted_and_confirmed_location_share_one_proposition_cluster() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故发生在北京。", "媒体甲"),
                article(2, "有关部门确认事故地点位于北京。", "媒体乙"),
            ]
        )
    )
    clusters = cluster_by_type(response, "location")

    assert len(clusters) == 1
    assert clusters[0].certainty == "mixed"
    assert clusters[0].certainty_values == ["asserted", "confirmed"]
    assert clusters[0].status == "supported"


def test_asserted_and_confirmed_casualty_share_one_proposition_cluster() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", "媒体甲"),
                article(2, "部门确认事故造成3人受伤。", "媒体乙"),
            ]
        )
    )

    assert len(cluster_by_type(response, "casualty")) == 1


def test_explicit_quantity_ignores_subject_anchor_but_keeps_measure_type() -> None:
    same_measure = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故损失3万元。", "媒体甲"),
                article(2, "经济损失为3万元。", "媒体乙"),
            ]
        )
    )
    different_measure = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故损失3万元。", "媒体甲"),
                article(2, "社会捐款3万元。", "媒体乙"),
            ]
        )
    )

    assert len(cluster_by_type(same_measure, "quantity")) == 1
    assert len(cluster_by_type(different_measure, "quantity")) == 2


def test_same_source_support_does_not_make_cluster_supported() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", "同一媒体", url="https://same.example/1"),
                article(2, "另一报道提到3人受伤。", "同一媒体", url="https://same.example/2"),
            ]
        )
    )
    cluster = cluster_by_type(response, "casualty")[0]
    support = relation_edge(response, "supports")

    assert support.attributes["independent_sources"] is False
    assert cluster.supporting_independent_source_count == 0
    assert cluster.status != "supported"


def test_two_independent_sources_make_cluster_supported() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", "媒体甲"),
                article(2, "另一报道提到3人受伤。", "媒体乙"),
            ]
        )
    )
    cluster = cluster_by_type(response, "casualty")[0]

    assert cluster.status == "supported"
    assert cluster.asserting_independent_source_count == 2
    assert cluster.supporting_independent_source_count == 2


@pytest.mark.parametrize(
    ("left_text", "right_text", "edge_type"),
    [
        ("事故造成3人受伤。", "另一报道提到3人受伤。", "supports"),
        ("事故造成3人受伤。", "另一报道提到5人受伤。", "contradicts"),
    ],
)
def test_symmetric_relation_metadata_is_stable_when_input_order_changes(
    left_text: str,
    right_text: str,
    edge_type: str,
) -> None:
    left = article(1, left_text, "媒体甲")
    right = article(2, right_text, "媒体乙")
    first = relation_edge(
        EvidenceGraphService().build(EventContext(articles=[left, right])),
        edge_type,
    )
    second = relation_edge(
        EvidenceGraphService().build(EventContext(articles=[right, left])),
        edge_type,
    )

    assert first == second
    assert first.attributes["symmetric"] is True
    assert first.quote == first.attributes["source_quote"]
    assert first.attributes["source_news_id"] in {1, 2}
    assert first.attributes["target_news_id"] in {1, 2}


def test_update_direction_and_quote_are_stable_when_input_order_changes() -> None:
    early = article(
        1,
        "10时救援工作已经展开。",
        "媒体甲",
        publish_time="2026-07-08 10:00:00",
    )
    late = article(
        2,
        "12时救援工作已经结束。",
        "媒体乙",
        publish_time="2026-07-08 12:00:00",
    )
    first = relation_edge(
        EvidenceGraphService().build(EventContext(articles=[early, late])),
        "updates",
    )
    second = relation_edge(
        EvidenceGraphService().build(EventContext(articles=[late, early])),
        "updates",
    )

    assert first == second
    assert first.attributes["symmetric"] is False
    assert first.attributes["source_news_id"] == 1
    assert first.attributes["target_news_id"] == 2
    assert first.attributes["source_quote"] == "10时救援工作已经展开"
    assert first.attributes["target_quote"] == "12时救援工作已经结束"
    assert first.quote == first.attributes["target_quote"]


def test_relation_budget_preserves_base_edges_and_logical_status() -> None:
    response = EvidenceGraphService(max_edges=1).build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", "媒体甲"),
                article(2, "另一报道提到3人受伤。", "媒体乙"),
                article(3, "第三个来源同样提到3人受伤。", "媒体丙"),
            ]
        )
    )
    cluster = cluster_by_type(response, "casualty")[0]
    claim_ids = {node.node_id for node in response.nodes if node.node_type == "claim"}
    article_ids = {node.node_id for node in response.nodes if node.node_type == "article"}

    assert cluster.status == "supported"
    assert response.metrics.support_edge_count == 2
    assert response.metrics.omitted_relation_edge_count == 1
    assert response.metrics.omitted_edge_count_by_type == {"supports": 1}
    assert response.metrics.logical_edge_count > response.metrics.returned_edge_count
    assert claim_ids <= {
        edge.target_node_id for edge in response.edges if edge.edge_type == "asserts"
    }
    assert article_ids <= {
        edge.target_node_id for edge in response.edges if edge.edge_type == "contains"
    }
    assert article_ids <= {
        edge.source_node_id for edge in response.edges if edge.edge_type == "published_by"
    }
    assert "evidence_graph_relation_edges_truncated" in response.risk_flags
    assert any("完整逻辑关系" in item for item in response.limitations)


def test_support_edges_grow_linearly_across_sources() -> None:
    contexts = [
        "现场救援简报显示",
        "医院接诊记录提到",
        "目击者采访材料称",
        "应急值守信息写明",
        "交通监控汇总指出",
        "后续情况说明提及",
    ]
    articles = [
        article(index, f"{context}事故造成3人受伤。", f"媒体{index}")
        for index, context in enumerate(contexts, start=1)
    ]

    response = EvidenceGraphService().build(EventContext(articles=articles))

    assert response.metrics.support_edge_count == len(articles) - 1


def test_conflict_ratio_is_cluster_based_and_edge_ratio_is_separate() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。事故发生在北京。", "媒体甲"),
                article(2, "事故造成5人受伤。", "媒体乙"),
            ]
        )
    )

    assert response.metrics.conflicting_cluster_count == 2
    assert response.metrics.verifiable_cluster_count == 3
    assert response.metrics.conflict_ratio == pytest.approx(2 / 3, abs=0.0001)
    assert response.metrics.contradiction_edge_ratio == 1.0


def test_not_verifiable_cluster_is_excluded_from_unresolved_ratio() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[article(1, "我认为这件事影响很大。", "媒体甲")]
        )
    )
    cluster = response.claim_clusters[0]

    assert cluster.status == "not_verifiable"
    assert cluster.verifiable is False
    assert response.metrics.verifiable_cluster_count == 0
    assert response.metrics.not_verifiable_cluster_count == 1
    assert response.metrics.unresolved_claim_ratio == 0
    assert "no_verifiable_graph_claims" in response.risk_flags
    assert "unresolved_claims_present" not in response.risk_flags


def test_mixed_date_precision_uses_publish_year_for_safe_ordering() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(
                    1,
                    "事故发生于2026年7月8日10时。",
                    "媒体甲",
                    publish_time="2026-07-08 11:00:00",
                ),
                article(
                    2,
                    "事故发生于7月9日10时。",
                    "媒体乙",
                    publish_time="2026-07-09 11:00:00",
                ),
            ]
        )
    )
    event_entries = [
        entry for entry in response.timeline if entry.claim_type == "event_time"
    ]

    assert [entry.time for entry in event_entries] == [
        "2026-07-08T10:00",
        "07-09T10:00",
    ]
    assert event_entries[0].time_precision == "full_datetime"
    assert event_entries[0].year_inferred is False
    assert event_entries[1].time_precision == "month_day_time"
    assert event_entries[1].year_inferred is True


@pytest.mark.parametrize(
    ("left", "right", "reason_code"),
    [
        (
            article(1, "事故造成3人受伤。", "媒体甲", url="https://a.example/1"),
            article(2, "事故造成3人受伤。", "媒体乙", url="https://b.example/2"),
            "same_normalized_body",
        ),
        (
            article(1, "事故造成3人受伤。", "媒体甲", url="https://same.example/a"),
            article(2, "事故造成3人受伤。", "媒体乙", url="https://same.example/a"),
            "same_normalized_url",
        ),
    ],
)
def test_duplicate_edges_include_reason_code(
    left: Article,
    right: Article,
    reason_code: str,
) -> None:
    response = EvidenceGraphService().build(EventContext(articles=[left, right]))
    duplicate = relation_edge(response, "duplicates")

    assert duplicate.reason_code == reason_code


def test_same_url_with_different_fact_signature_is_not_duplicate() -> None:
    response = EvidenceGraphService().build(
        EventContext(
            articles=[
                article(1, "事故造成3人受伤。", "媒体甲", url="https://same.example/a"),
                article(2, "事故造成5人受伤。", "媒体乙", url="https://same.example/a"),
            ]
        )
    )

    assert response.metrics.duplicate_article_count == 0
    assert "same_url_with_fact_difference" in response.risk_flags
    assert "contradicts" in {edge.edge_type for edge in response.edges}
