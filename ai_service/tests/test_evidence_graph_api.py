from copy import deepcopy

from app.core.config import Settings
from app.llm.deepseek_provider import DeepSeekProvider


def graph_event(event_payload: dict, articles: list[dict]) -> dict:
    event = deepcopy(event_payload)
    event["articles"] = articles
    return event


def graph_article(
    news_id: int,
    content: str,
    *,
    source: str,
    url: str | None = None,
    publish_time: str = "2026-07-08 10:00:00",
) -> dict:
    return {
        "news_id": news_id,
        "title": f"报道{news_id}",
        "content": content,
        "source": source,
        "url": url or f"https://source-{news_id}.example/{news_id}",
        "publish_time": publish_time,
        "platform": "新闻网站",
    }


def test_evidence_graph_api_returns_complete_top_level_structure(
    client,
    event_payload,
) -> None:
    event = graph_event(
        event_payload,
        [
            graph_article(1, "事故造成3人受伤。", source="媒体甲"),
            graph_article(2, "另一报道显示事故造成3人受伤。", source="媒体乙"),
        ],
    )

    response = client.post("/ai/evidence-graph", json={"event": event})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "event_id",
        "summary",
        "nodes",
        "edges",
        "claim_clusters",
        "timeline",
        "metrics",
        "key_findings",
        "risk_flags",
        "limitations",
        "analysis_method",
        "fallback_used",
    }
    assert {node["node_type"] for node in payload["nodes"]} == {
        "event",
        "article",
        "source",
        "claim",
    }
    assert {edge["edge_type"] for edge in payload["edges"]} >= {
        "contains",
        "published_by",
        "asserts",
        "supports",
    }


def test_evidence_graph_output_is_stable_for_same_input(client, event_payload) -> None:
    event = graph_event(
        event_payload,
        [
            graph_article(1, "事故造成3人受伤。", source="媒体甲"),
            graph_article(2, "事故造成5人受伤。", source="媒体乙"),
        ],
    )

    first = client.post("/ai/evidence-graph", json={"event": event}).json()
    second = client.post("/ai/evidence-graph", json={"event": event}).json()

    assert first == second


def test_evidence_graph_openapi_is_registered_without_changing_existing_paths(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/ai/evidence-graph" in paths
    assert "post" in paths["/ai/evidence-graph"]
    assert "/health" in paths
    assert "/ai/ask" in paths
    assert "/ai/report" in paths
    assert "/ai/verify" in paths


def test_empty_event_produces_valid_empty_graph(client, event_payload) -> None:
    response = client.post(
        "/ai/evidence-graph",
        json={"event": graph_event(event_payload, [])},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["nodes"]) == 1
    assert payload["edges"] == []
    assert payload["claim_clusters"] == []
    assert payload["metrics"]["article_count"] == 0
    assert "no_graph_claims" in payload["risk_flags"]


def test_graph_response_does_not_expose_truth_probability(client, event_payload) -> None:
    event = graph_event(
        event_payload,
        [graph_article(1, "事故造成3人受伤。", source="媒体甲")],
    )

    payload = client.post("/ai/evidence-graph", json={"event": event}).json()
    serialized = str(payload).lower()

    assert "evidence_score" not in serialized
    assert "truth_probability" not in serialized
    assert any("不是真实性概率" in item for item in payload["limitations"])


def test_evidence_graph_limits_have_stable_defaults(monkeypatch) -> None:
    for name in (
        "AI_EVIDENCE_GRAPH_MAX_ARTICLES",
        "AI_EVIDENCE_GRAPH_MAX_CLAIMS_PER_ARTICLE",
        "AI_EVIDENCE_GRAPH_MAX_EDGES",
        "AI_EVIDENCE_GRAPH_ARTICLE_MAX_CHARS",
    ):
        monkeypatch.delenv(name, raising=False)

    configured = Settings(llm_provider="fake")

    assert configured.evidence_graph_llm_enabled is True
    assert configured.evidence_graph_max_articles == 12
    assert configured.evidence_graph_max_claims_per_article == 5
    assert configured.evidence_graph_max_nodes == 40
    assert configured.evidence_graph_max_edges == 60
    assert configured.evidence_graph_article_max_chars == 6000


def test_evidence_graph_does_not_depend_on_llm_provider(
    client,
    event_payload,
    monkeypatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("evidence graph must not call DeepSeek")

    monkeypatch.setattr(DeepSeekProvider, "generate", fail_if_called)
    event = graph_event(
        event_payload,
        [graph_article(1, "事故造成3人受伤。", source="媒体甲")],
    )

    response = client.post("/ai/evidence-graph", json={"event": event})

    assert response.status_code == 200
