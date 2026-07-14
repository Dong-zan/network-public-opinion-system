from app.schemas.verification import VerificationEvidence
from app.services.verification_service import VerificationService


def evidence(news_id, source: str, url: str) -> VerificationEvidence:
    return VerificationEvidence(
        news_id=news_id,
        source=source,
        url=url,
        quote="事故造成3人受伤。",
        stance="supports",
    )


def test_same_hostname_with_different_source_names_is_one_cluster() -> None:
    items = [
        evidence(1, "媒体甲", "https://same.example/a"),
        evidence(2, "媒体乙", "https://same.example/b"),
    ]

    support, _ = VerificationService._stance_clusters(items)

    assert len(support) == 1


def test_same_source_with_different_hostnames_is_one_cluster() -> None:
    items = [
        evidence(1, "媒体甲", "https://one.example/a"),
        evidence(2, "媒体甲", "https://two.example/b"),
    ]

    support, _ = VerificationService._stance_clusters(items)

    assert len(support) == 1


def test_different_source_and_hostname_can_form_two_clusters() -> None:
    items = [
        evidence(1, "媒体甲", "https://one.example/a"),
        evidence(2, "媒体乙", "https://two.example/b"),
    ]

    support, _ = VerificationService._stance_clusters(items)

    assert len(support) == 2
