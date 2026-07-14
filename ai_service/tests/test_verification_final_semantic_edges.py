from app.schemas.event import Article, EventContext
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier
from app.services.verification_service import VerificationService


def article(
    news_id: int,
    content: str,
    source: str = "测试来源",
    publish_time: str = "2026-07-08 10:00:00",
) -> Article:
    return Article(
        news_id=news_id,
        content=content,
        source=f"{source}{news_id}",
        url=f"https://source-{news_id}.example/{news_id}",
        publish_time=publish_time,
    )


def claim_of_type(text: str, claim_type: str):
    return next(
        claim
        for claim in ClaimExtractor().extract(Article(content=text), 10)
        if claim.claim_type == claim_type
    )


def classify(
    target: str,
    evidence: str,
    claim_type: str,
    *,
    target_publish_time: str | None = None,
    evidence_publish_time: str | None = None,
):
    return StanceClassifier().classify(
        claim_of_type(target, claim_type),
        evidence,
        target_publish_time=target_publish_time,
        evidence_publish_time=evidence_publish_time,
    )


def test_month_day_reference_time_orders_rescue_updates() -> None:
    decision = classify(
        "7月8日10时救援工作已经展开。",
        "7月9日10时救援工作已经结束。",
        "response_status",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "response_status_evolved"


def test_month_day_reference_time_orders_casualty_updates() -> None:
    decision = classify(
        "7月8日10时事故造成3人受伤。",
        "7月9日10时事故造成5人受伤。",
        "casualty",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "casualty_information_evolved"


def test_same_month_day_reference_time_keeps_status_conflict() -> None:
    decision = classify(
        "7月8日10时救援工作已经展开。",
        "7月8日10时救援工作尚未展开。",
        "response_status",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "contradicts"


def test_mixed_reference_time_precision_does_not_fall_back_to_publish_time() -> None:
    decision = classify(
        "7月8日10时救援工作已经展开。",
        "10时救援工作已经结束。",
        "response_status",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "response_status_conflict"


def test_noon_one_is_equivalent_to_thirteen() -> None:
    decision = classify(
        "事故发生于中午1时。",
        "事故发生于13时。",
        "event_time",
    )

    assert decision.stance == "supports"


def test_noon_one_is_not_equivalent_to_one() -> None:
    decision = classify(
        "事故发生于中午1时。",
        "事故发生于1时。",
        "event_time",
    )

    assert decision.stance == "contradicts"


def test_afternoon_twelve_is_equivalent_to_twelve_colon_zero() -> None:
    decision = classify(
        "事故发生于下午12时。",
        "事故发生时间为12:00。",
        "event_time",
    )

    assert decision.stance == "supports"


def test_evening_eight_is_equivalent_to_twenty() -> None:
    decision = classify(
        "事故发生于晚上8时。",
        "事故发生于20:00。",
        "event_time",
    )

    assert decision.stance == "supports"


def test_supported_chinese_periods_are_normalized() -> None:
    cases = {
        "凌晨1时": "01:00",
        "早上8时": "08:00",
        "上午10时": "10:00",
        "中午12时": "12:00",
        "中午1时": "13:00",
        "下午1时": "13:00",
        "晚上8时": "20:00",
    }

    for expression, expected in cases.items():
        claim = claim_of_type(f"事故发生于{expression}。", "event_time")
        assert claim.slots["event_time"] == expected


def test_invalid_hour_does_not_create_event_time_slot() -> None:
    extracted = ClaimExtractor().extract(Article(content="事故发生于25时。"), 10)

    assert all(claim.claim_type != "event_time" for claim in extracted)


def test_bare_police_refutation_context_does_not_negate_following_location() -> None:
    location = claim_of_type("警方辟谣后表示事故发生在北京。", "location")

    assert location.polarity == "affirmative"
    assert location.modality_reason is None


def test_explicit_police_refutation_negates_embedded_location() -> None:
    location = claim_of_type("警方辟谣称事故发生在北京系不实。", "location")

    assert location.polarity == "negative"
    assert location.modality_reason == "claim_explicitly_refuted"


def test_message_not_true_structure_negates_only_embedded_location() -> None:
    location = claim_of_type("警方称事故发生在北京的消息不属实。", "location")

    assert location.slots["city"] == "北京"
    assert location.polarity == "negative"
    assert location.modality_reason == "claim_explicitly_refuted"


def test_completed_refutation_context_does_not_negate_casualty() -> None:
    casualty = claim_of_type("警方完成辟谣后表示3人受伤。", "casualty")

    assert casualty.polarity == "affirmative"


def test_rumor_suffix_explicitly_negates_embedded_casualty() -> None:
    casualty = claim_of_type("网传3人死亡系谣言。", "casualty")

    assert casualty.polarity == "negative"
    assert casualty.modality_reason == "claim_explicitly_refuted"


def test_refutation_in_second_clause_does_not_negate_first_location() -> None:
    extracted = ClaimExtractor().extract(
        Article(content="事故发生在上海，网传3人死亡系谣言。"),
        10,
    )
    location = next(claim for claim in extracted if claim.claim_type == "location")

    assert location.slots["city"] == "上海"
    assert location.polarity == "affirmative"


def test_later_positive_casualty_updates_zero_casualty() -> None:
    decision = classify(
        "无人员伤亡。",
        "事故造成3人受伤。",
        "casualty",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "casualty_information_evolved"


def test_later_positive_casualty_updates_temporary_zero_casualty() -> None:
    decision = classify(
        "暂无人员伤亡。",
        "事故造成3人受伤。",
        "casualty",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "updates"


def test_temporary_zero_casualty_phrases_remain_unconfirmed() -> None:
    for text in ("暂无人员伤亡。", "尚无人员伤亡。"):
        claim = claim_of_type(text, "casualty")
        assert claim.certainty == "unconfirmed"


def test_same_reference_time_zero_and_positive_casualty_conflict() -> None:
    decision = classify(
        "截至10时，无人员伤亡。",
        "截至10时，事故造成3人受伤。",
        "casualty",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "contradicts"


def test_zero_casualty_update_is_context_only_and_does_not_raise_score() -> None:
    event = EventContext(
        articles=[
            article(1, "无人员伤亡。", publish_time="2026-07-08 10:00:00"),
            article(2, "事故造成3人受伤。", publish_time="2026-07-08 12:00:00"),
        ]
    )

    result = VerificationService().verify(event, 1).claim_results[0]

    assert result.evidence == []
    assert result.independent_source_count == 0
    assert result.evidence_score == 0
    assert result.context_evidence[0].relation == "updates"
    assert result.context_evidence[0].quote == "事故造成3人受伤。"


def test_full_administrative_location_is_structured() -> None:
    location = claim_of_type("事故发生在广东省深圳市南山区。", "location")

    assert location.slots["province"] == "广东"
    assert location.slots["city"] == "深圳"
    assert location.slots["district"] == "南山区"


def test_city_and_full_administrative_location_are_compatible() -> None:
    for city, full in (
        ("深圳", "广东省深圳市南山区"),
        ("杭州", "浙江省杭州市余杭区"),
    ):
        decision = classify(
            f"事故发生在{city}。",
            f"事故发生在{full}。",
            "location",
        )
        assert decision.stance == "related"
        assert decision.reason_code == "location_parent_child_compatible"


def test_different_generic_cities_are_contradictory() -> None:
    decision = classify("事故发生在深圳。", "事故发生在广州。", "location")

    assert decision.stance == "contradicts"


def test_city_name_and_same_named_road_are_not_administratively_compatible() -> None:
    decision = classify("事故发生在北京。", "事故发生在北京路。", "location")

    assert decision.stance == "related"
    assert decision.reason_code == "location_not_comparable"


def test_equivalent_municipality_district_formats_support_each_other() -> None:
    decision = classify(
        "事故发生在北京市朝阳区。",
        "事故发生在北京朝阳区。",
        "location",
    )

    assert decision.stance == "supports"
