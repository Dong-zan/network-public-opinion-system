import pytest

from app.schemas.event import Article, EventContext
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier
from app.services.verification_service import VerificationService


def article(
    news_id: int,
    content: str,
    source: str | None = None,
) -> Article:
    return Article(
        news_id=news_id,
        content=content,
        source=source or f"来源{news_id}",
        url=f"https://source-{news_id}.example/{news_id}",
        publish_time="2026-07-08 10:00:00",
    )


def claims(text: str, max_claims: int = 10):
    return ClaimExtractor().extract(Article(content=text), max_claims)


def location_claim(text: str):
    return next(item for item in claims(text) if item.claim_type == "location")


@pytest.mark.parametrize(
    "evidence",
    [
        "事故发生地点为深圳市福田区。",
        "事发地点为深圳市福田区。",
        "事故地点是深圳市福田区。",
        "事故地点位于深圳市福田区。",
        "事发地是深圳市福田区。",
    ],
)
def test_location_assignment_expressions_detect_district_conflict(evidence: str) -> None:
    extracted = location_claim(evidence)
    decision = StanceClassifier().classify(
        location_claim("事故发生在深圳市南山区。"),
        evidence,
    )

    assert extracted.slots["city"] == "深圳"
    assert extracted.slots["district"] == "福田区"
    assert decision.stance == "contradicts"
    assert decision.reason_code == "location_district_conflict"


def test_two_futian_sources_produce_strong_contradicted_verdict() -> None:
    event = EventContext(
        articles=[
            article(1, "事故发生在深圳市南山区。", "媒体甲"),
            article(2, "事故发生地点为深圳市福田区。", "媒体乙"),
            article(3, "有关部门确认事故发生在广东省深圳市福田区。", "媒体丙"),
        ]
    )

    response = VerificationService().verify(event, 1)
    result = response.claim_results[0]

    assert response.overall_verdict == "contradicted"
    assert result.verdict == "contradicted"
    assert result.independent_source_count == 2
    assert result.evidence_score == 90
    assert response.evidence_score == 90


def test_city_and_district_are_compatible_and_same_district_is_supported() -> None:
    city_to_district = StanceClassifier().classify(
        location_claim("事故发生在深圳。"),
        "事故地点为深圳市福田区。",
    )
    same_district = StanceClassifier().classify(
        location_claim("事故发生在深圳市福田区。"),
        "事故地点为广东省深圳市福田区。",
    )

    assert city_to_district.stance == "related"
    assert city_to_district.reason_code == "location_parent_child_compatible"
    assert same_district.stance == "supports"


def test_as_of_time_prefix_creates_one_casualty_with_reference_time() -> None:
    extracted = claims("截至12时，事故造成3人受伤。")
    casualties = [item for item in extracted if item.claim_type == "casualty"]

    assert len(extracted) == 1
    assert len(casualties) == 1
    assert casualties[0].slots["count"] == 3
    assert casualties[0].slots["casualty_type"] == "injured"
    assert casualties[0].slots["reference_time"]["event_time"] == "12:00"
    assert all(item.claim_type != "other" for item in extracted)


def test_date_time_prefix_creates_one_response_status_with_reference_time() -> None:
    extracted = claims("7月8日10时，救援工作已经展开。")
    statuses = [item for item in extracted if item.claim_type == "response_status"]

    assert len(extracted) == 1
    assert len(statuses) == 1
    reference = statuses[0].slots["reference_time"]
    assert reference["event_date"] == "07-08"
    assert reference["event_time"] == "10:00"
    assert all(item.claim_type != "other" for item in extracted)


def test_as_of_observational_zero_creates_one_casualty() -> None:
    extracted = claims("截至10时，未发现人员伤亡。")

    assert len(extracted) == 1
    assert extracted[0].claim_type == "casualty"
    assert extracted[0].slots["count"] == 0
    assert extracted[0].slots["reference_time"]["event_time"] == "10:00"


def test_real_multi_fact_casualties_are_not_merged() -> None:
    extracted = [
        item
        for item in claims("事故造成1人死亡、3人受伤。")
        if item.claim_type == "casualty"
    ]

    assert len(extracted) == 2
    assert {(item.slots["count"], item.slots["casualty_type"]) for item in extracted} == {
        (1, "dead"),
        (3, "injured"),
    }


def test_time_location_and_casualty_remain_three_distinct_claims() -> None:
    extracted = claims("2026年7月8日10时，北京发生事故造成3人受伤。")

    assert len(extracted) == 3
    assert {item.claim_type for item in extracted} == {
        "event_time",
        "location",
        "casualty",
    }
    assert all(item.claim_type != "other" for item in extracted)


def test_max_claims_is_applied_after_semantic_deduplication() -> None:
    extracted = claims(
        "截至12时，事故造成3人受伤。事故发生在深圳市南山区。",
        max_claims=2,
    )

    assert len(extracted) == 2
    assert {item.claim_type for item in extracted} == {"casualty", "location"}


def test_unique_claim_restores_verification_statistics() -> None:
    event = EventContext(
        articles=[
            article(1, "截至12时，事故造成3人受伤。"),
            article(2, "截至12时，事故造成5人受伤。"),
            article(3, "截至12时，另一来源称事故中共有5人受伤。"),
        ]
    )

    response = VerificationService().verify(event, 1)

    assert len(response.claim_results) == 1
    assert response.verifiable_claim_count == 1
    assert response.determinate_claim_count == 1
    assert response.verification_coverage == 100
    assert "limited_independent_sources" not in response.risk_flags


def test_time_prefixed_status_is_counted_once() -> None:
    event = EventContext(
        articles=[
            article(1, "7月8日10时，救援工作已经展开。"),
            article(2, "7月8日12时，救援工作已经结束。"),
        ]
    )

    response = VerificationService().verify(event, 1)

    assert len(response.claim_results) == 1
    assert response.verifiable_claim_count == 1
    assert response.claim_results[0].context_evidence[0].relation == "updates"


def test_time_prefix_does_not_break_refutation_scope() -> None:
    extracted = claims("截至12时，事故发生在上海，网传3人死亡系谣言。")
    location = next(item for item in extracted if item.claim_type == "location")
    casualty = next(item for item in extracted if item.claim_type == "casualty")

    assert location.polarity == "affirmative"
    assert casualty.polarity == "negative"


def test_verify_openapi_declares_not_found_response(client) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/ai/verify"]["post"]

    assert "404" in operation["responses"]
    assert operation["responses"]["404"]["description"] == "待核验文章不在当前事件数据中"
