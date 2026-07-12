from app.schemas.verification import ClaimVerificationResult, VerificationEvidence
from app.services.verification_scorer import VerificationScorer


def supporting_result() -> ClaimVerificationResult:
    return ClaimVerificationResult(
        claim_id=1,
        claim="事故造成3人受伤",
        verdict="supported",
        independent_source_count=2,
        evidence=[
            VerificationEvidence(
                news_id=2,
                source="媒体乙",
                quote="事故造成3人受伤。",
                stance="supports",
            )
        ],
    )


def test_not_verifiable_claim_does_not_lower_evidence_strength() -> None:
    scorer = VerificationScorer()
    supported = supporting_result()
    not_verifiable = ClaimVerificationResult(
        claim_id=2,
        claim="未来可能继续发展",
        verdict="not_verifiable",
        independent_source_count=0,
    )

    assert scorer.score([supported, not_verifiable]) == scorer.score([supported])


def test_no_evidence_means_zero_strength() -> None:
    result = ClaimVerificationResult(
        claim_id=1,
        claim="事故造成3人受伤",
        verdict="insufficient_evidence",
        independent_source_count=0,
    )

    assert VerificationScorer().score([result]) == 0
