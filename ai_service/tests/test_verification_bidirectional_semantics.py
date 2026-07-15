from app.schemas.event import Article, EventContext
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier
from app.services.verification_service import VerificationService


def article(
    news_id: int,
    content: str,
    publish_time: str = "2026-07-08 10:00:00",
) -> Article:
    return Article(
        news_id=news_id,
        content=content,
        source=f"来源{news_id}",
        url=f"https://source-{news_id}.example/{news_id}",
        publish_time=publish_time,
    )


def claims(text: str):
    return ClaimExtractor().extract(Article(content=text), 10)


def claim_of_type(text: str, claim_type: str):
    return next(item for item in claims(text) if item.claim_type == claim_type)


def classify(
    target: str,
    evidence: str,
    claim_type: str,
    *,
    target_time: str | None = None,
    evidence_time: str | None = None,
):
    return StanceClassifier().classify(
        claim_of_type(target, claim_type),
        evidence,
        target_publish_time=target_time,
        evidence_publish_time=evidence_time,
    )


def test_later_target_casualty_treats_earlier_zero_as_update() -> None:
    decision = classify(
        "事故造成3人受伤。",
        "无人员伤亡。",
        "casualty",
        target_time="2026-07-08 12:00:00",
        evidence_time="2026-07-08 10:00:00",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "target_is_later_information_update"


def test_later_target_rescue_treats_earlier_status_as_update() -> None:
    decision = classify(
        "救援工作已经结束。",
        "救援工作已经展开。",
        "response_status",
        target_time="2026-07-08 12:00:00",
        evidence_time="2026-07-08 10:00:00",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "target_is_later_information_update"


def test_conclusion_progression_is_detected_in_both_directions() -> None:
    forward = classify(
        "目前形成初步调查结论。",
        "最终调查结论已经形成。",
        "conclusion_status",
        target_time="2026-07-08 10:00:00",
        evidence_time="2026-07-08 12:00:00",
    )
    reverse = classify(
        "最终调查结论已经形成。",
        "目前形成初步调查结论。",
        "conclusion_status",
        target_time="2026-07-08 12:00:00",
        evidence_time="2026-07-08 10:00:00",
    )

    assert forward.stance == "updates"
    assert forward.reason_code == "conclusion_status_evolved"
    assert reverse.stance == "updates"
    assert reverse.reason_code == "target_is_later_information_update"


def test_reverse_update_is_context_only_and_marks_evolving_information() -> None:
    event = EventContext(
        articles=[
            article(1, "事故造成3人受伤。", "2026-07-08 12:00:00"),
            article(2, "无人员伤亡。", "2026-07-08 10:00:00"),
        ]
    )

    response = VerificationService().verify(event, 1)
    result = response.claim_results[0]

    assert result.evidence == []
    assert result.independent_source_count == 0
    assert result.evidence_score == 0
    assert result.context_evidence[0].relation == "updates"
    assert result.context_evidence[0].reason_code == "target_is_later_information_update"
    assert "evolving_information" in response.risk_flags


def test_multi_fact_evidence_prefers_matching_injury_claim() -> None:
    decision = classify(
        "事故造成3人受伤。",
        "事故造成1人死亡、3人受伤。",
        "casualty",
    )

    assert decision.stance == "supports"
    assert decision.reason_code == "same_casualty_type_and_count"


def test_multi_fact_evidence_prefers_matching_death_claim() -> None:
    decision = classify(
        "事故造成1人死亡。",
        "事故造成1人死亡、3人受伤。",
        "casualty",
    )

    assert decision.stance == "supports"


def test_multi_fact_evidence_reports_same_type_count_conflict() -> None:
    decision = classify(
        "事故造成5人受伤。",
        "事故造成1人死亡、3人受伤。",
        "casualty",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "casualty_count_conflict"


def test_two_multi_fact_sources_do_not_create_false_high_score_contradiction() -> None:
    event = EventContext(
        articles=[
            article(1, "事故造成3人受伤。"),
            article(2, "现场报告同时提到1人死亡、3人受伤。"),
            article(3, "另一份详细统计记载死亡1人，另有3人受伤。"),
        ]
    )

    response = VerificationService().verify(event, 1)
    result = response.claim_results[0]

    assert result.verdict == "supported"
    assert all(item.reason_code == "same_casualty_type_and_count" for item in result.evidence)


def test_compact_multi_fact_claims_match_their_own_casualty_types() -> None:
    target_claims = [item for item in claims("事故造成1死3伤。") if item.claim_type == "casualty"]

    decisions = [
        StanceClassifier().classify(item, "另一报道显示事故造成1死3伤。")
        for item in target_claims
    ]

    assert len(decisions) == 2
    assert all(item.stance == "supports" for item in decisions)


def test_rescue_reference_time_does_not_leak_into_event_time() -> None:
    extracted = claims("事故发生在北京，10时救援工作已经展开。")
    rescue = next(item for item in extracted if item.claim_type == "response_status")

    assert all(item.claim_type != "event_time" for item in extracted)
    assert rescue.slots["reference_time"]["event_time"] == "10:00"


def test_casualty_reference_time_does_not_leak_into_event_time() -> None:
    extracted = claims("事故发生在北京，截至12时共有3人受伤。")
    casualty = next(item for item in extracted if item.claim_type == "casualty")

    assert all(item.claim_type != "event_time" for item in extracted)
    assert casualty.slots["reference_time"]["event_time"] == "12:00"


def test_local_event_occurrence_time_is_still_extracted() -> None:
    for text in ("事故于10时发生。", "10时发生事故。"):
        event_time = claim_of_type(text, "event_time")
        assert event_time.slots["event_time"] == "10:00"


def test_time_prefix_before_occurrence_clause_is_event_time() -> None:
    event_time = claim_of_type("7月8日10时，北京发生事故。", "event_time")

    assert event_time.slots["event_date"] == "07-08"
    assert event_time.slots["event_time"] == "10:00"


def test_leaked_event_time_cannot_form_a_verification_claim() -> None:
    target_claims = claims("事故发生在北京，10时救援工作已经展开。")
    evidence_claims = claims("事故发生在北京，10时救援工作已经展开。")

    assert not any(item.claim_type == "event_time" for item in target_claims)
    assert not any(item.claim_type == "event_time" for item in evidence_claims)


def test_same_city_different_districts_are_contradictory() -> None:
    for target, evidence in (
        ("深圳市南山区", "深圳市福田区"),
        ("广东省深圳市南山区", "广东省深圳市福田区"),
    ):
        decision = classify(
            f"事故发生在{target}。",
            f"事故发生在{evidence}。",
            "location",
        )
        assert decision.stance == "contradicts"
        assert decision.reason_code == "location_district_conflict"


def test_city_and_district_remain_parent_child_compatible() -> None:
    decision = classify(
        "事故发生在深圳。",
        "事故发生在深圳市南山区。",
        "location",
    )

    assert decision.stance == "related"
    assert decision.reason_code == "location_parent_child_compatible"


def test_same_district_with_optional_province_is_supported() -> None:
    decision = classify(
        "事故发生在深圳市南山区。",
        "事故发生在广东省深圳市南山区。",
        "location",
    )

    assert decision.stance == "supports"


def test_beijing_and_beijing_road_remain_unrelated_locations() -> None:
    decision = classify("事故发生在北京。", "事故发生在北京路。", "location")

    assert decision.stance == "related"
    assert decision.reason_code == "location_not_comparable"


def test_not_found_casualty_phrases_are_observational_zero_claims() -> None:
    phrases = (
        "未发现人员伤亡。",
        "暂未发现人员伤亡。",
        "尚未发现人员伤亡。",
        "未发现伤亡。",
        "暂未发现伤亡。",
    )

    for text in phrases:
        claim = claim_of_type(text, "casualty")
        assert claim.slots["count"] == 0
        assert claim.slots["casualty_type"] == "generic_casualty"
        assert claim.polarity == "affirmative"
        assert claim.certainty == "unconfirmed"
        assert claim.modality_reason == "claim_modality_unconfirmed"


def test_earlier_not_found_casualty_is_updated_by_later_injury() -> None:
    decision = classify(
        "未发现人员伤亡。",
        "事故造成3人受伤。",
        "casualty",
        target_time="2026-07-08 10:00:00",
        evidence_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "updates"


def test_later_injury_is_not_contradicted_by_earlier_not_found_casualty() -> None:
    decision = classify(
        "事故造成3人受伤。",
        "未发现人员伤亡。",
        "casualty",
        target_time="2026-07-08 12:00:00",
        evidence_time="2026-07-08 10:00:00",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "target_is_later_information_update"


def test_same_reference_time_not_found_zero_and_injury_conflict() -> None:
    decision = classify(
        "截至10时未发现人员伤亡。",
        "截至10时事故造成3人受伤。",
        "casualty",
        target_time="2026-07-08 10:00:00",
        evidence_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "contradicts"
