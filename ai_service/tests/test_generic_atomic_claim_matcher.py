from dataclasses import replace

from app.schemas.event import Article
from app.services.claim_extractor import ClaimExtractor
from app.services.generic_atomic_claim_matcher import GenericAtomicClaimMatcher
from app.services.stance_classifier import StanceClassifier


def claim(text: str):
    return ClaimExtractor().extract(Article(content=text), 1)[0]


def test_semantically_equivalent_social_post_is_supported() -> None:
    decision = StanceClassifier().classify(
        claim("某明星在社交平台发布生日动态"),
        "某明星生日当天通过社交平台分享庆生照片和生活动态",
    )

    assert decision.stance == "supports"
    assert decision.reason_code == "generic_semantic_support"


def test_recent_time_context_does_not_change_subject_identity() -> None:
    decision = StanceClassifier().classify(
        claim("近日，某明星在社交平台发布生日动态"),
        "某明星生日当天通过社交平台分享庆生照片和生活动态",
    )

    assert decision.stance == "supports"
    assert decision.reason_code == "generic_semantic_support"


def test_different_predicate_is_only_related() -> None:
    decision = StanceClassifier().classify(
        claim("某明星举办线下生日活动"),
        "某明星发布生日照片",
    )

    assert decision.stance == "related"
    assert decision.reason_code == "generic_predicate_mismatch"


def test_structured_casualty_rule_is_preserved() -> None:
    decision = StanceClassifier().classify(
        claim("某事故造成10人死亡"),
        "官方通报造成8人死亡",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "casualty_count_conflict"


def test_generic_negation_conflicts_with_affirmative_fact() -> None:
    decision = StanceClassifier().classify(
        claim("某明星没有发布生日动态"),
        "某明星发布生日照片",
    )

    assert decision.stance == "contradicts"
    assert decision.reason_code == "generic_polarity_conflict"


def test_structured_fields_take_priority_over_text_parsing() -> None:
    target = replace(
        claim("某明星分享照片"),
        subject="某明星",
        predicate="publish",
        object="生日动态",
        polarity="affirmative",
        certainty="asserted",
    )
    evidence = claim("某明星发布生日动态")

    decision = GenericAtomicClaimMatcher().match(target, evidence)

    assert decision.stance == "supports"
    assert decision.reason_code == "generic_semantic_support"
