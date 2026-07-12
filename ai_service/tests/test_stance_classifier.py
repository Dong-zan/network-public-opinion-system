from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier


def claim(text: str):
    return ClaimExtractor().extract(Article(content=text), 1)[0]


def test_same_count_different_casualty_type_is_not_supported() -> None:
    decision = StanceClassifier().classify(
        claim("事故造成3人受伤。"),
        "事故造成3人死亡。",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "casualty_type_conflict"


def test_different_locations_are_contradictory() -> None:
    decision = StanceClassifier().classify(
        claim("事故发生在北京。"),
        "事故发生在上海。",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "location_conflict"


def test_different_event_times_are_contradictory() -> None:
    decision = StanceClassifier().classify(
        claim("事故发生于10时。"),
        "事故发生于11时。",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "event_time_conflict"


def test_started_and_completed_response_are_not_supported() -> None:
    decision = StanceClassifier().classify(
        claim("救援工作已经展开。"),
        "救援工作已经结束。",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "response_status_conflict"


def test_cause_under_investigation_is_only_related_to_specific_cause() -> None:
    decision = StanceClassifier().classify(
        claim("设备老化导致事故。"),
        "事故具体原因仍在调查。",
    )

    assert decision.stance == "related"
    assert decision.reason_code == "cause_still_under_investigation"


def test_text_similarity_alone_never_produces_support_for_other_claim() -> None:
    decision = StanceClassifier().classify(
        claim("现场情况受到广泛关注。"),
        "现场情况受到广泛关注。",
    )

    assert decision.stance == "related"
