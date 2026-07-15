from app.schemas.event import Article, EventContext
from app.services.claim_extractor import ClaimExtractor
from app.services.stance_classifier import StanceClassifier
from app.services.verification_service import VerificationService


def article(news_id, content: str, source: str, publish_time: str) -> Article:
    return Article(
        news_id=news_id,
        content=content,
        source=source,
        url=f"https://source-{news_id}.example/{news_id}",
        publish_time=publish_time,
    )


def first_claim(text: str):
    return ClaimExtractor().extract(Article(content=text), 1)[0]


def test_later_completed_rescue_is_temporal_update() -> None:
    decision = StanceClassifier().classify(
        first_claim("救援工作已经展开。"),
        "救援工作已经结束。",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "response_status_evolved"


def test_same_time_started_and_not_started_are_contradictory() -> None:
    decision = StanceClassifier().classify(
        first_claim("救援工作已经展开。"),
        "救援工作尚未展开。",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 10:00:00",
    )

    assert decision.stance == "contradicts"


def test_later_casualty_count_is_evolving_information() -> None:
    decision = StanceClassifier().classify(
        first_claim("事故造成3人受伤。"),
        "后续报道称事故造成5人受伤。",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "updates"
    assert decision.reason_code == "casualty_information_evolved"


def test_same_reference_time_casualty_counts_conflict() -> None:
    target = next(
        claim
        for claim in ClaimExtractor().extract(Article(content="截至10时，事故造成3人受伤。"), 10)
        if claim.claim_type == "casualty"
    )
    decision = StanceClassifier().classify(
        target,
        "截至10时，事故造成5人受伤。",
        target_publish_time="2026-07-08 10:00:00",
        evidence_publish_time="2026-07-08 12:00:00",
    )

    assert decision.stance == "contradicts"


def test_service_marks_evolving_information() -> None:
    event = EventContext(
        articles=[
            article(1, "救援工作已经展开。", "媒体甲", "2026-07-08 10:00:00"),
            article(2, "救援工作已经结束。", "媒体乙", "2026-07-08 12:00:00"),
        ]
    )

    response = VerificationService().verify(event, 1)

    assert response.overall_verdict == "insufficient_evidence"
    assert "evolving_information" in response.risk_flags
    assert any("信息演化" in item for item in response.limitations)
