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


def test_single_support_relation_has_strength_before_stable_verdict() -> None:
    result = ClaimVerificationResult(
        claim_id=1,
        claim="某明星发布生日动态",
        verdict="insufficient_evidence",
        independent_source_count=1,
        evidence=[
            VerificationEvidence(
                news_id=2,
                source="媒体乙",
                quote="某明星分享生日动态。",
                stance="supports",
            )
        ],
    )

    assert VerificationScorer().score_claim(result) == 30


def test_two_independent_support_sources_have_high_strength() -> None:
    result = ClaimVerificationResult(
        claim_id=1,
        claim="某明星发布生日动态",
        verdict="supported",
        independent_source_count=2,
        evidence=[
            VerificationEvidence(
                news_id=2,
                source="媒体乙",
                quote="某明星分享生日动态。",
                stance="supports",
            ),
            VerificationEvidence(
                news_id=3,
                source="媒体丙",
                quote="某明星发布庆生照片。",
                stance="supports",
            ),
        ],
    )

    assert VerificationScorer().score_claim(result) >= 80


def test_partial_support_is_not_zeroed_by_insufficient_overall_verdict() -> None:
    supported_atom = ClaimVerificationResult(
        claim_id=1,
        claim="某明星发布生日动态",
        verdict="insufficient_evidence",
        independent_source_count=1,
        evidence=[
            VerificationEvidence(
                news_id=2,
                source="媒体乙",
                quote="某明星分享生日动态。",
                stance="supports",
            )
        ],
        evidence_score=30,
    )
    no_evidence_atom = ClaimVerificationResult(
        claim_id=2,
        claim="某明星举办生日活动",
        verdict="insufficient_evidence",
        independent_source_count=0,
        evidence_score=0,
    )

    score = VerificationScorer().score(
        [supported_atom, no_evidence_atom],
        overall_verdict="insufficient_evidence",
    )

    assert score == 15
    assert score > 0


def test_weighted_article_score_uses_parent_evidence_strength() -> None:
    first_parent = ClaimVerificationResult(
        claim_id=1,
        claim="复合主张一",
        verdict="insufficient_evidence",
        independent_source_count=1,
        evidence_score=15,
    )
    second_parent = ClaimVerificationResult(
        claim_id=2,
        claim="主张二",
        verdict="insufficient_evidence",
        independent_source_count=0,
        evidence_score=0,
    )

    assert VerificationScorer().score(
        [first_parent, second_parent],
        overall_verdict="insufficient_evidence",
        weights=[2, 1],
    ) == 10
