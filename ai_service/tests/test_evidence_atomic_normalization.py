from app.schemas.event import Article, EventContext
from app.services.verification_service import VerificationService


def verify(target: str, evidence: str):
    event = EventContext(
        articles=[
            Article(news_id=1, content=target, source="目标来源"),
            Article(
                news_id=2,
                content=evidence,
                source="证据来源",
                url="https://evidence.example/2",
            ),
        ]
    )
    return VerificationService().verify(event, 1)


def test_evidence_sentence_is_atomized_before_generic_matching() -> None:
    response = verify(
        "某明星在社交平台发布生日动态。",
        "某明星生日当天通过社交平台分享庆生照片和生活动态。",
    )

    atom = response.atomic_claims[0]

    assert atom.relation_results[0].relation == "supports"
    assert atom.relation_results[0].reason_code == "generic_semantic_support"


def test_different_evidence_predicate_remains_related() -> None:
    response = verify(
        "某明星举办庆祝活动。",
        "某明星发布生日照片。",
    )

    atom = response.atomic_claims[0]

    assert atom.relation_results[0].relation == "related"
    assert atom.relation_results[0].reason_code == "generic_predicate_mismatch"


def test_legacy_structured_claim_comparison_is_preserved() -> None:
    response = verify(
        "某事故造成10人死亡。",
        "官方通报某事故造成8人死亡。",
    )

    atom = response.atomic_claims[0]

    assert atom.relation_results[0].relation == "contradicts"
    assert atom.relation_results[0].reason_code == "casualty_count_conflict"
