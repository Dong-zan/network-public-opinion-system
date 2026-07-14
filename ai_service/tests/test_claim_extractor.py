from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor


def extract(content: str, max_claims: int = 5):
    return ClaimExtractor().extract(Article(content=content), max_claims)


def test_casualty_claim_contains_structured_slots_and_exact_quote() -> None:
    content = "事故造成3人受伤。"

    claim = extract(content)[0]

    assert claim.claim_type == "casualty"
    assert claim.slots == {"count": 3, "unit": "人", "casualty_type": "injured"}
    assert claim.target_quote in content


def test_incomplete_attribution_is_not_an_atomic_claim() -> None:
    claims = extract("据警方通报，事故造成3人受伤。")

    assert all(claim.text != "据警方通报" for claim in claims)
    assert claims[0].target_quote == "事故造成3人受伤"


def test_claims_are_ranked_before_max_claims_is_applied() -> None:
    claims = extract("天气较热。有人围观。事故造成3人受伤。事故发生在北京。", max_claims=2)

    assert [claim.claim_type for claim in claims] == ["casualty", "location"]


def test_duplicate_structured_claims_are_stably_removed() -> None:
    claims = extract("事故造成3人受伤。另据报道，事故造成3人受伤。")

    casualty_claims = [claim for claim in claims if claim.claim_type == "casualty"]
    assert len(casualty_claims) == 1


def test_future_and_minor_are_not_treated_as_negated_facts() -> None:
    future = extract("未来救援工作将继续。", max_claims=1)[0]
    minor = extract("未成年人已经得到安置。", max_claims=1)[0]

    assert future.certainty != "denied"
    assert minor.certainty != "denied"
