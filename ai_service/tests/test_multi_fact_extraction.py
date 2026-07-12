from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor


def test_one_sentence_extracts_time_location_and_casualty() -> None:
    content = "2026年7月8日10时，北京发生事故造成3人受伤。"

    claims = ClaimExtractor().extract(Article(content=content), 10)

    assert {claim.claim_type for claim in claims} >= {
        "event_time",
        "location",
        "casualty",
    }
    assert all(claim.target_quote in content for claim in claims)
