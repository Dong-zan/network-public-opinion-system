from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier


def event_time_claim(text: str):
    return next(
        claim
        for claim in ClaimExtractor().extract(Article(content=text), 10)
        if claim.claim_type == "event_time"
    )


def test_full_chinese_datetime_preserves_date_hour_and_datetime() -> None:
    claim = event_time_claim("事故发生于2026年7月8日10时。")

    assert claim.slots == {
        "event_date": "2026-07-08",
        "event_time": "10:00",
        "event_datetime": "2026-07-08T10:00",
    }


def test_same_date_different_hours_are_contradictory() -> None:
    decision = StanceClassifier().classify(
        event_time_claim("事故发生于2026年7月8日10时。"),
        "事故发生于2026年7月8日11时。",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "event_time_conflict"


def test_hour_and_colon_time_are_equivalent() -> None:
    decision = StanceClassifier().classify(
        event_time_claim("事故发生于10时。"),
        "事故发生时间为10:00。",
    )

    assert decision.stance == "supports"


def test_date_present_on_only_one_side_is_related() -> None:
    decision = StanceClassifier().classify(
        event_time_claim("事故发生于2026年7月8日10时。"),
        "事故发生于10时。",
    )

    assert decision.stance == "related"
    assert decision.reason_code == "event_time_partial_match"


def test_publish_time_is_not_extracted_as_event_time() -> None:
    article = Article(
        content="现场正在处置。",
        publish_time="2026-07-08 10:00:00",
    )

    claims = ClaimExtractor().extract(article, 10)

    assert all(claim.claim_type != "event_time" for claim in claims)
