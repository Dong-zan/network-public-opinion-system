from copy import deepcopy


def article(news_id, content: str, source: str, url: str) -> dict:
    return {
        "news_id": news_id,
        "title": "核验报道",
        "content": content,
        "source": source,
        "url": url,
        "publish_time": "2026-07-08 10:00:00",
    }


def post_verify(client, event_payload: dict, articles: list[dict]):
    event = deepcopy(event_payload)
    event["articles"] = articles
    return client.post(
        "/ai/verify",
        json={"event": event, "target_news_id": 1, "max_claims": 5},
    )


def test_all_not_verifiable_adds_flag_and_limitation(client, event_payload) -> None:
    response = post_verify(
        client,
        event_payload,
        [article(1, "我认为这件事影响很大。", "媒体甲", "https://one.example/a")],
    )

    payload = response.json()
    assert payload["overall_verdict"] == "not_verifiable"
    assert "no_verifiable_claims" in payload["risk_flags"]
    assert any("未提取到当前阶段可确定性核验" in item for item in payload["limitations"])


def test_user_visible_text_does_not_expose_internal_enums(client, event_payload) -> None:
    response = post_verify(
        client,
        event_payload,
        [
            article(1, "事故造成3人受伤。", "媒体甲", "https://one.example/a"),
            article(2, "事故造成3人死亡。", "媒体乙", "https://two.example/a"),
            article(3, "另一报道确认3人死亡。", "媒体丙", "https://three.example/a"),
        ],
    )

    payload = response.json()
    visible = " ".join(
        [payload["score_explanation"], *payload["limitations"]]
        + [item.get("explanation") or "" for item in payload["claim_results"]]
    )
    for internal in (
        "casualty",
        "location",
        "event_time",
        "supported",
        "contradicted",
        "conflicting",
        "insufficient_evidence",
        "not_verifiable",
    ):
        assert internal not in visible


def test_strong_contradiction_score_is_not_diluted_by_insufficient_claims(
    client,
    event_payload,
) -> None:
    target = (
        "事故造成3人受伤。现场有群众围观。天气情况受到关注。"
        "道路通行受到影响。事件引发讨论。"
    )
    response = post_verify(
        client,
        event_payload,
        [
            article(1, target, "媒体甲", "https://one.example/a"),
            article(2, "事故造成3人死亡。", "媒体乙", "https://two.example/a"),
            article(3, "另一报道确认3人死亡。", "媒体丙", "https://three.example/a"),
        ],
    )

    payload = response.json()
    assert payload["overall_verdict"] == "contradicted"
    assert payload["evidence_score"] >= 80
    assert payload["verification_coverage"] < 100


def test_duplicate_news_id_is_rejected_with_422(client, event_payload) -> None:
    response = post_verify(
        client,
        event_payload,
        [
            article(1, "事故造成3人受伤。", "媒体甲", "https://one.example/a"),
            article(1, "另一篇不同正文。", "媒体乙", "https://two.example/a"),
        ],
    )

    assert response.status_code == 422
    assert "news_id必须唯一" in response.text
