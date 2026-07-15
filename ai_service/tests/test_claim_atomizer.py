from app.schemas.event import Article, EventContext
from app.schemas.verification import AtomicClaimResult
from app.services.claim_atomizer import ClaimAtomizer
from app.services.claim_extractor import ClaimExtractor
from app.services.verification_service import VerificationService


def texts(value: str) -> list[str]:
    return [item.text for item in ClaimAtomizer().atomize(value)]


def test_atomizes_bing_and_inherits_subject() -> None:
    result = texts("某明星发布照片，并举办活动")

    assert result == ["某明星发布照片", "某明星举办活动"]


def test_atomizes_bingqie_and_inherits_subject() -> None:
    result = texts("某明星发布生日动态并且举办庆祝活动")

    assert result == ["某明星发布生日动态", "某明星举办庆祝活动"]


def test_atomizes_tongshi_and_inherits_time_and_location() -> None:
    result = texts("昨日某明星在北京发布照片，同时举办活动")

    assert result == [
        "昨日某明星在北京发布照片",
        "昨日某明星在北京举办活动",
    ]


def test_atomizes_multiple_predicates_from_parent_claim() -> None:
    result = texts(
        "某明星迎来生日，在社交平台发布生日动态，并举办庆祝活动"
    )

    assert result == [
        "某明星迎来生日",
        "某明星在社交平台发布生日动态",
        "某明星举办庆祝活动",
    ]


def test_does_not_split_he_connected_objects() -> None:
    result = texts("某明星发布照片和视频")

    assert result == ["某明星发布照片和视频"]


def test_inherits_reported_modality() -> None:
    result = texts("据称某明星发布照片，并举办活动")

    assert result == ["据称某明星发布照片", "据称某明星举办活动"]


def test_inherits_suspected_modality() -> None:
    result = texts("疑似某明星发布照片，同时举办活动")

    assert result == ["疑似某明星发布照片", "疑似某明星举办活动"]


def test_preserves_scoped_negation_without_leaking_it() -> None:
    result = texts("某明星未发布照片，并举办活动")

    assert result == ["某明星未发布照片", "某明星举办活动"]


def test_preserves_explicit_negation_on_each_atom() -> None:
    result = texts("某明星未发布照片，并且未举办活动")

    assert result == ["某明星未发布照片", "某明星未举办活动"]


def test_verification_keeps_claim_results_and_adds_atomic_claims() -> None:
    event = EventContext(
        event_id=199,
        articles=[
            Article(
                news_id=501,
                content="某明星发布照片，并举办活动。",
                source="目标来源",
            )
        ],
    )

    response = VerificationService().verify(event, 501)

    assert response.claim_results
    assert response.atomic_claims
    assert response.atomic_claims[0].parent_claim
    assert {item.claim for item in response.atomic_claims} == {
        "某明星发布照片",
        "某明星举办活动",
    }


def test_atomic_claim_enters_evidence_retrieval_before_parent_aggregation() -> None:
    event = EventContext(
        event_id=199,
        articles=[
            Article(
                news_id=501,
                content=(
                    "某明星迎来生日，在社交平台发布生日动态，"
                    "并举办庆祝活动。"
                ),
                source="目标来源",
            ),
            Article(
                news_id=502,
                content=(
                    "某明星生日当天通过社交平台分享庆生照片和生活动态。"
                ),
                source="独立来源",
                url="https://evidence.example/502",
            ),
        ],
    )

    response = VerificationService().verify(event, 501)

    assert len(response.atomic_claims) >= 3
    publishing = next(
        item for item in response.atomic_claims
        if "发布生日动态" in item.claim
    )
    assert publishing.parent_claim == (
        "某明星迎来生日，在社交平台发布生日动态，并举办庆祝活动"
    )
    assert publishing.subject == "某明星"
    assert publishing.predicate == "publish"
    assert publishing.object == "生日动态"
    assert publishing.relation_results
    assert publishing.relation_results[0].news_id == 502
    assert publishing.relation_results[0].relation == "supports"
    assert publishing.verdict == "insufficient_evidence"
    assert publishing.evidence_score == 30
    assert response.claim_results[0].claim == publishing.parent_claim
    assert response.claim_results[0].evidence_score > 0
    assert response.overall_verdict == "insufficient_evidence"
    assert response.evidence_score > 0


def test_atomic_claims_include_conservative_fact_structure() -> None:
    atoms = ClaimAtomizer().atomize(
        "近日，某明星迎来生日，在社交平台发布生日动态，并举办庆祝活动"
    )

    assert len(atoms) == 3
    assert (
        atoms[0].subject,
        atoms[0].predicate,
        atoms[0].object,
        atoms[0].time,
    ) == ("某明星", "birthday", None, "近日")
    assert (
        atoms[1].subject,
        atoms[1].predicate,
        atoms[1].object,
        atoms[1].time,
    ) == ("某明星", "publish", "生日动态", "近日")
    assert (
        atoms[2].subject,
        atoms[2].predicate,
        atoms[2].object,
        atoms[2].time,
    ) == ("某明星", "hold_activity", "庆祝活动", "近日")
    assert atoms[1].inherited_context["subject"] == "某明星"
    assert atoms[2].inherited_context["time"] == "近日"


def test_atomic_structure_inherits_location() -> None:
    atoms = ClaimAtomizer().atomize(
        "某明星在北京发布照片，同时举办活动"
    )

    assert [item.location for item in atoms] == ["北京", "北京"]
    assert atoms[1].inherited_context["location"] == "北京"


def test_atomic_structure_preserves_negative_polarity() -> None:
    atoms = ClaimAtomizer().atomize(
        "某明星未发布照片，并且未举办活动"
    )

    assert [item.polarity for item in atoms] == ["negative", "negative"]


def test_atomic_structure_inherits_modality() -> None:
    atoms = ClaimAtomizer().atomize(
        "据称某明星发布照片，并举办活动"
    )

    assert [item.certainty for item in atoms] == ["unconfirmed", "unconfirmed"]
    assert atoms[1].inherited_context["modality"] == "据称"
    assert atoms[1].inherited_context["certainty"] == "unconfirmed"


def test_unparseable_atomic_structure_remains_empty() -> None:
    atom = ClaimAtomizer().atomize("现场情况受到广泛关注")[0]

    assert atom.subject is None
    assert atom.predicate is None
    assert atom.object is None
    assert atom.claim_type is None
    assert atom.time is None
    assert atom.location is None
    assert atom.polarity is None
    assert atom.certainty is None
    assert atom.inherited_context == {}


def test_existing_structured_claim_extraction_is_unchanged() -> None:
    claim = ClaimExtractor().extract(
        Article(content="某事故造成10人死亡"),
        1,
    )[0]

    assert claim.claim_type == "casualty"
    assert claim.slots == {
        "count": 10,
        "unit": "人",
        "casualty_type": "dead",
    }


def test_old_atomic_result_json_remains_valid() -> None:
    result = AtomicClaimResult.model_validate(
        {
            "atomic_claim_id": 1,
            "parent_claim_id": 1,
            "parent_claim": "旧父主张",
            "claim": "旧原子主张",
            "verdict": "insufficient_evidence",
            "independent_source_count": 0,
        }
    )

    assert result.subject is None
    assert result.predicate is None
    assert result.object is None
    assert result.inherited_context == {}
