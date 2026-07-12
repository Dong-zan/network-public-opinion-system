from app.schemas.event import Article, EventContext
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier
from app.services.verification_service import VerificationService


def article(
    news_id: int,
    content: str,
    source: str,
    publish_time: str = "2026-07-08 10:00:00",
) -> Article:
    return Article(
        news_id=news_id,
        content=content,
        source=source,
        url=f"https://source-{news_id}.example/{news_id}",
        publish_time=publish_time,
    )


def claims(text: str):
    return ClaimExtractor().extract(Article(content=text), 10)


def claim_of_type(text: str, claim_type: str):
    return next(item for item in claims(text) if item.claim_type == claim_type)


def verify(target: str, *evidence: str):
    articles = [article(1, target, "媒体甲")]
    articles.extend(
        article(index, content, f"媒体{index}")
        for index, content in enumerate(evidence, start=2)
    )
    return VerificationService().verify(EventContext(articles=articles), 1)


def test_refuted_location_is_not_extracted_as_affirmative() -> None:
    location = claim_of_type("事故发生在北京系不实信息。", "location")

    assert location.slots["normalized_name"] == "北京"
    assert location.polarity == "negative"
    assert location.modality_reason == "claim_explicitly_refuted"


def test_police_refutation_conflicts_with_affirmative_location_evidence() -> None:
    response = verify(
        "警方辟谣称事故发生在北京系不实信息。",
        "报道明确事故发生在北京。",
        "另一来源确认事故发生在北京。",
    )

    result = response.claim_results[0]
    assert result.verdict == "contradicted"
    assert all(item.reason_code == "claim_explicitly_refuted" for item in result.evidence)


def test_rumor_explicitly_refuted_is_never_supported_as_affirmative() -> None:
    response = verify(
        "网传事故造成3人死亡系谣言。",
        "报道明确事故造成3人死亡。",
        "另一来源称事故造成3人死亡。",
    )

    assert response.claim_results[0].verdict != "supported"


def test_plain_rumor_target_is_unconfirmed_and_not_supported() -> None:
    target = claim_of_type("网传事故造成3人死亡。", "casualty")
    response = verify(
        "网传事故造成3人死亡。",
        "报道提到事故造成3人死亡。",
        "另一来源称事故造成3人死亡。",
    )

    assert target.certainty == "unconfirmed"
    assert target.polarity == "unknown"
    assert target.modality_reason == "claim_reported_as_rumor"
    assert response.claim_results[0].verdict == "insufficient_evidence"


def test_rumor_attribution_before_comma_keeps_unconfirmed_modality() -> None:
    target = claim_of_type("有消息称，事故造成3人死亡。", "casualty")

    assert target.certainty == "unconfirmed"
    assert target.polarity == "unknown"
    assert target.modality_reason == "claim_reported_as_rumor"


def test_possible_and_suspected_casualties_are_unconfirmed() -> None:
    possible = claim_of_type("事故可能造成3人受伤。", "casualty")
    suspected = claim_of_type("事故疑似造成5人受伤。", "casualty")

    assert possible.certainty == suspected.certainty == "unconfirmed"
    assert possible.polarity == suspected.polarity == "unknown"
    assert possible.modality_reason == suspected.modality_reason == "claim_modality_unconfirmed"


def test_two_rumor_sources_do_not_form_supported_evidence() -> None:
    response = verify(
        "事故造成3人受伤。",
        "网传事故造成3人受伤。",
        "据传事故造成3人受伤。",
    )

    result = response.claim_results[0]
    assert result.verdict == "insufficient_evidence"
    assert result.independent_source_count == 0
    assert result.context_evidence
    assert all(item.relation == "related" for item in result.context_evidence)


def test_negative_location_word_orders_contradict_affirmative_location() -> None:
    classifier = StanceClassifier()
    for target_text in ("事故并非在北京发生。", "事故不是在北京发生。"):
        decision = classifier.classify(
            claim_of_type(target_text, "location"),
            "事故发生在北京。",
        )
        assert decision.stance == "contradicts"


def test_negative_event_time_word_order_contradicts_affirmative_time() -> None:
    decision = StanceClassifier().classify(
        claim_of_type("事故并非在10时发生。", "event_time"),
        "事故发生于10时。",
    )

    assert decision.stance == "contradicts"


def test_future_and_minor_words_are_not_negation_markers() -> None:
    extracted = claims("北京未来科技公司发布公告。未成年人获得妥善安置。")

    assert all(item.polarity != "negative" for item in extracted)


def test_same_reference_time_rescue_status_is_contradictory() -> None:
    decision = StanceClassifier().classify(
        claim_of_type("10时救援工作已经展开。", "response_status"),
        "10时救援工作尚未展开。",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "contradicts"


def test_later_reference_time_rescue_status_is_update() -> None:
    decision = StanceClassifier().classify(
        claim_of_type("10时救援工作已经展开。", "response_status"),
        "12时救援工作已经结束。",
        target_publish_time="2026-07-08 12:00:00",
        evidence_publish_time="2026-07-08 10:00:00",
    )

    assert decision.stance == "updates"


def test_reference_time_takes_priority_over_later_publish_time() -> None:
    decision = StanceClassifier().classify(
        claim_of_type("10时救援工作已经展开。", "response_status"),
        "10时救援工作尚未展开。",
        target_publish_time="2026-07-08 09:00:00",
        evidence_publish_time="2026-07-08 15:00:00",
    )

    assert decision.stance == "contradicts"


def test_reference_time_is_separate_from_event_occurrence_time() -> None:
    casualty = claim_of_type("截至12时共有5人受伤。", "casualty")
    investigation = claim_of_type("当日15时调查仍在进行。", "conclusion_status")

    assert casualty.slots["reference_time"]["event_time"] == "12:00"
    assert investigation.slots["reference_time"]["event_time"] == "15:00"
    assert not any(item.claim_type == "event_time" for item in claims("截至12时共有5人受伤。"))


def test_zero_casualty_expressions_are_extracted() -> None:
    confirmed = claim_of_type("事故未造成人员伤亡。", "casualty")
    temporary = claim_of_type("现场暂无人员伤亡。", "casualty")

    assert confirmed.slots == {"count": 0, "unit": "人", "casualty_type": "generic_casualty"}
    assert temporary.certainty == "unconfirmed"


def test_zero_casualty_conflicts_with_injuries() -> None:
    decision = StanceClassifier().classify(
        claim_of_type("事故未造成人员伤亡。", "casualty"),
        "事故造成3人受伤。",
    )

    assert decision.stance == "contradicts"


def test_compact_casualties_create_multiple_atomic_claims() -> None:
    extracted = [item for item in claims("事故造成1死3伤。") if item.claim_type == "casualty"]

    assert {(item.slots["count"], item.slots["casualty_type"]) for item in extracted} == {
        (1, "dead"),
        (3, "injured"),
    }


def test_multiple_casualty_groups_create_multiple_atomic_claims() -> None:
    extracted = [
        item
        for item in claims("事故造成3人死亡、5人受伤。")
        if item.claim_type == "casualty"
    ]

    assert {(item.slots["count"], item.slots["casualty_type"]) for item in extracted} == {
        (3, "dead"),
        (5, "injured"),
    }


def test_missing_and_hospitalized_groups_are_both_extracted() -> None:
    extracted = [
        item
        for item in claims("事故中2人失踪，另有4人送医。")
        if item.claim_type == "casualty"
    ]

    assert {(item.slots["count"], item.slots["casualty_type"]) for item in extracted} == {
        (2, "missing"),
        (4, "hospitalized"),
    }


def test_refutation_scope_does_not_negate_unrelated_clause() -> None:
    extracted = claims("救援工作已经展开，网传事故造成3人死亡系谣言。")
    rescue = next(item for item in extracted if item.claim_type == "response_status")
    casualty = next(item for item in extracted if item.claim_type == "casualty")

    assert rescue.polarity == "affirmative"
    assert casualty.polarity == "negative"


def test_context_evidence_returns_valid_updates_quote_without_scoring_it() -> None:
    event = EventContext(
        articles=[
            article(1, "10时救援工作已经展开。", "媒体甲", "2026-07-08 12:00:00"),
            article(2, "12时救援工作已经结束。", "媒体乙", "2026-07-08 10:00:00"),
        ]
    )

    response = VerificationService().verify(event, 1)
    result = response.claim_results[0]

    assert result.context_evidence[0].relation == "updates"
    assert result.context_evidence[0].quote in event.articles[1].content
    assert result.independent_source_count == 0
    assert result.evidence_score == 0


def test_context_evidence_returns_valid_related_quote_without_scoring_it() -> None:
    response = verify(
        "事故造成3人受伤。",
        "网传事故造成3人受伤。",
    )
    result = response.claim_results[0]

    assert result.context_evidence[0].relation == "related"
    assert result.context_evidence[0].quote == "网传事故造成3人受伤。"
    assert result.independent_source_count == 0
    assert result.evidence_score == 0


def test_truncated_duplicate_candidate_is_reported_even_when_not_selected() -> None:
    common_prefix = "事故信息正在整理。" * 20
    event = EventContext(
        articles=[
            article(1, "事故造成3人受伤。", "媒体甲"),
            article(2, common_prefix + "事故造成3人受伤。", "媒体乙"),
            article(3, common_prefix + "事故造成5人受伤。", "媒体丙"),
        ]
    )

    response = VerificationService(article_max_chars=40).verify(event, 1)

    assert "verification_input_truncated" in response.risk_flags
    assert any("正文超过" in item for item in response.limitations)
