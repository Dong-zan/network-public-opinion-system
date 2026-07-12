from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier


def quantity_claim(text: str):
    return next(
        claim
        for claim in ClaimExtractor().extract(Article(content=text), 10)
        if claim.claim_type == "quantity"
    )


def test_same_amount_with_different_measure_type_is_not_supported() -> None:
    target = quantity_claim("事故经济损失3万元。")
    decision = StanceClassifier().classify(target, "社会捐款3万元。")

    assert target.slots["measure_type"] == "economic_loss"
    assert decision.stance == "related"
    assert decision.reason_code == "quantity_measure_type_mismatch"
