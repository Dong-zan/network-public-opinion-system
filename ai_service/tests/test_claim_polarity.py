from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier


def claim(text: str):
    return ClaimExtractor().extract(Article(content=text), 1)[0]


def test_negative_location_conflicts_with_same_affirmative_location() -> None:
    target = claim("事故未发生在北京。")
    decision = StanceClassifier().classify(target, "事故发生在北京。")

    assert target.polarity == "negative"
    assert decision.stance == "contradicts"
    assert decision.reason_code == "polarity_conflict"


def test_negative_time_conflicts_with_same_affirmative_time() -> None:
    target = claim("事故并非发生于10时。")
    decision = StanceClassifier().classify(target, "事故发生于10时。")

    assert target.polarity == "negative"
    assert decision.stance == "contradicts"


def test_negative_casualty_rules_compare_exact_proposition() -> None:
    classifier = StanceClassifier()
    target = claim("事故未造成3人受伤。")

    assert classifier.classify(target, "事故造成3人受伤。").stance == "contradicts"
    assert classifier.classify(target, "事故造成5人受伤。").stance == "related"
    assert classifier.classify(target, "事故未造成5人受伤。").stance == "related"


def test_future_and_minor_remain_affirmative_not_negative() -> None:
    future = claim("未来救援工作将继续。")
    minor = claim("未成年人已经得到安置。")

    assert future.polarity == "affirmative"
    assert minor.polarity == "affirmative"
    assert future.certainty in {"asserted", "confirmed", "unconfirmed"}
    assert minor.certainty in {"asserted", "confirmed", "unconfirmed"}
