from copy import deepcopy

from app.services.verification_explanation_validator import (
    VerificationAIExplanationValidator,
)


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


def test_related_multi_article_material_has_nonzero_score_and_concise_display(
    client,
    event_payload,
) -> None:
    response = post_verify(
        client,
        event_payload,
        [
            article(
                1,
                "逐玉衍生演唱会于8月15日在深圳举行，已公布部分参演阵容。",
                "极目新闻",
                "https://one.example/concert",
            ),
            article(
                79,
                "逐玉演唱会定档8月15日深圳，公开阵容包括李怀安、俞浅浅等艺人。",
                "中国蓝新闻",
                "https://two.example/concert",
            ),
            article(
                158,
                "演唱会将于8月15日在深圳举行，报道同时讨论男女主缺席阵容。",
                "都市现场",
                "https://three.example/concert",
            ),
        ],
    )

    payload = response.json()
    assert payload["evidence_score"] > 0
    display = payload["display_result"]
    assert display["uncertainties"] == [
        "本次共比较3篇事件材料，重点呈现共同信息、报道差异与来源关系；结论对应当前材料范围。"
    ]
    assert len(display["reasons"]) <= 5
    visible = " ".join(
        [display["headline"], display["conclusion"], *display["reasons"]]
        + display["uncertainties"]
        + [item["explanation"] for item in display["evidence_cards"]]
    )
    for forbidden in (
        "news_id",
        "event_id",
        "heat",
        "sentiment",
        "independent_source_count",
    ):
        assert forbidden not in visible
    assert visible.count("证据不足") <= 1
    assert visible.count("无法核验") <= 1


def test_verify_text_filter_naturalizes_raw_field_names_and_rejects_object_repr() -> None:
    validator = VerificationAIExplanationValidator()
    text = validator._naturalize_user_text(
        "报道（news_id 79）对应event_id=3，heat为27，sentiment偏正面。"
    )

    assert "news_id" not in text
    assert "event_id" not in text
    assert "heat" not in text
    assert "sentiment" not in text
    assert validator._INTERNAL_REPRESENTATION_PATTERN.search(
        "Article(news_id=79, source='媒体')"
    )
    assert validator._INTERNAL_REPRESENTATION_PATTERN.search(
        "{'news_id': 79, 'source': '媒体'}"
    )
