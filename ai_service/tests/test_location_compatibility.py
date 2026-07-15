from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier


def location_claim(text: str):
    return next(
        claim
        for claim in ClaimExtractor().extract(Article(content=text), 10)
        if claim.claim_type == "location"
    )


def test_city_and_district_are_parent_child_compatible() -> None:
    decision = StanceClassifier().classify(
        location_claim("事故发生在北京。"),
        "事故发生在北京市朝阳区。",
    )

    assert decision.stance == "related"
    assert decision.reason_code == "location_parent_child_compatible"


def test_different_cities_are_contradictory() -> None:
    decision = StanceClassifier().classify(
        location_claim("事故发生在北京。"),
        "事故发生在上海。",
    )

    assert decision.stance == "contradicts"


def test_beijing_road_is_not_treated_as_beijing_parent_location() -> None:
    decision = StanceClassifier().classify(
        location_claim("事故发生在北京。"),
        "事故发生在北京路。",
    )

    assert decision.stance == "related"
    assert decision.reason_code == "location_not_comparable"
