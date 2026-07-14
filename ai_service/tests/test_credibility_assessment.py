from copy import deepcopy

from app.schemas.event import Article, EventContext
from app.schemas.verification import VerificationResponse
from app.services.credibility_assessment_service import CredibilityAssessmentService
from app.services.language_risk import DeterministicLanguageRiskAnalyzer
from app.services.source_registry import SourceProfile, StaticSourceRegistry
from app.services.source_traceability import SourceTraceabilityEvaluator
from app.services.verification_service import VerificationService


def article(news_id: int, content: str, source: str, url: str, **extra) -> dict:
    return {
        "news_id": news_id,
        "title": "普通标题",
        "content": content,
        "source": source,
        "url": url,
        "publish_time": "2026-07-13 10:00:00",
        "platform": "新闻网站",
        **extra,
    }


def event(articles: list[dict]) -> EventContext:
    return EventContext.model_validate({"event_id": 1, "articles": articles, "analysis": {}})


def registry() -> StaticSourceRegistry:
    return StaticSourceRegistry(
        (SourceProfile(canonical_name="测试日报", verified_domains=("news.test.local",)),)
    )


def assessment_service() -> CredibilityAssessmentService:
    return CredibilityAssessmentService(
        source_evaluator=SourceTraceabilityEvaluator(registry())
    )


def test_new_article_fields_are_optional_and_response_is_backward_compatible() -> None:
    parsed_article = Article.model_validate({"news_id": 1})
    legacy = VerificationResponse.model_validate(
        {
            "target_news_id": 1,
            "overall_verdict": "not_verifiable",
            "evidence_score": 0,
            "score_type": "heuristic_evidence_score",
            "score_explanation": "旧响应说明。",
        }
    )

    assert parsed_article.reference_urls == []
    assert parsed_article.quoted_news_ids == []
    assert parsed_article.author is None
    assert legacy.credibility_assessment is None
    assert legacy.ai_explanation is None


def test_single_verified_source_stays_insufficient_and_not_low_risk() -> None:
    items = [article(1, "事故造成3人受伤。", "测试日报", "https://news.test.local/1")]
    result = VerificationService(credibility_assessment_service=assessment_service()).verify(event(items), 1)

    assert result.overall_verdict == "insufficient_evidence"
    assert result.credibility_assessment is not None
    assert result.credibility_assessment.source_assessment.status == "verified"
    assert result.credibility_assessment.risk_label != "low"


def test_unknown_source_is_neutral_not_high_by_itself() -> None:
    target = Article.model_validate(article(1, "事故造成3人受伤。", "未知来源", "https://example.com/1"))
    source = SourceTraceabilityEvaluator(registry()).evaluate(target)

    assert source.status == "unknown"
    assert source.risk_score == 50
    assert source.risk_score != 100


def test_unconfigured_registry_uses_metadata_without_registration_penalty() -> None:
    target = Article.model_validate(
        article(1, "事故造成3人受伤。", "滨江发布", "https://example.com/1")
    )

    source = SourceTraceabilityEvaluator().evaluate(target)

    assert source.status == "unknown"
    assert source.registered_source is None
    assert source.domain_match is None
    assert source.risk_score == 15


def test_missing_real_source_metadata_increases_source_risk() -> None:
    complete = Article.model_validate(
        article(1, "事故造成3人受伤。", "滨江发布", "https://example.com/1")
    )
    sparse = Article.model_validate(
        article(
            2,
            "事故造成3人受伤。",
            "",
            "",
            publish_time=None,
        )
    )
    evaluator = SourceTraceabilityEvaluator()

    assert evaluator.evaluate(complete).risk_score < evaluator.evaluate(sparse).risk_score


def test_credibility_scoring_version_marks_metadata_only_source_logic() -> None:
    result = VerificationService().verify(
        event([article(1, "事故造成3人受伤。", "滨江发布", "https://example.com/1")]),
        1,
    )

    assert result.credibility_assessment.version == "credibility-risk-v1.1"


def test_registry_name_with_wrong_domain_is_mismatch_and_example_com_not_verified() -> None:
    target = Article.model_validate(article(1, "事故造成3人受伤。", "测试日报", "https://example.com/1"))
    source = SourceTraceabilityEvaluator(registry()).evaluate(target)

    assert source.status == "mismatch"
    assert source.domain_match is False
    assert source.hostname == "example.com"


def test_deterministic_language_flags_and_measurement_exception() -> None:
    analyzer = DeterministicLanguageRiskAnalyzer()
    risky = Article.model_validate(
        article(1, "原因已经百分百确定。惊天内幕。据不愿透露姓名的内部人士称，官方肯定在隐瞒真相。", "来源", "https://example.com/1")
    )
    neutral_measurement = Article.model_validate(
        article(2, "工程完成率达到100%，电池电量为100%，统计覆盖率100%。", "来源", "https://example.com/2")
    )

    flags = analyzer.analyze(risky).flags
    assert {flag.type for flag in flags} >= {"absolute_claim", "sensational_language", "anonymous_attribution", "conspiracy_claim"}
    assert all(flag.quote in risky.title or flag.quote in risky.content for flag in flags)
    assert not any(flag.type == "absolute_claim" for flag in analyzer.analyze(neutral_measurement).flags)


def test_target_source_metadata_does_not_change_fact_verdict_or_claim_results() -> None:
    base = [
        article(1, "事故造成3人受伤。", "来源甲", "https://source-a.local/1"),
        article(2, "事故造成3人受伤。", "来源乙", "https://source-b.local/2"),
        article(3, "事故造成3人受伤。", "来源丙", "https://source-c.local/3"),
    ]
    changed = deepcopy(base)
    changed[0].update({"source": "测试日报", "url": "https://example.com/1", "is_official": True})
    service = VerificationService(credibility_assessment_service=assessment_service())
    first = service.verify(event(base), 1)
    second = service.verify(event(changed), 1)

    assert first.overall_verdict == second.overall_verdict
    assert first.claim_results == second.claim_results
    assert first.credibility_assessment.source_assessment != second.credibility_assessment.source_assessment


def test_target_tone_changes_language_but_not_fact_verdict_or_claims() -> None:
    base = [
        article(1, "事故造成3人受伤。", "来源甲", "https://source-a.local/1", title="普通标题"),
        article(2, "事故造成3人受伤。", "来源乙", "https://source-b.local/2"),
        article(3, "事故造成3人受伤。", "来源丙", "https://source-c.local/3"),
    ]
    changed = deepcopy(base)
    changed[0]["title"] = "惊天内幕"
    service = VerificationService()
    first = service.verify(event(base), 1)
    second = service.verify(event(changed), 1)

    assert first.overall_verdict == second.overall_verdict
    assert first.claim_results == second.claim_results
    assert first.credibility_assessment.language_assessment != second.credibility_assessment.language_assessment


def test_two_independent_contradictions_enforce_high_risk_floor() -> None:
    items = [
        article(1, "事故造成3人受伤。", "来源甲", "https://source-a.local/1"),
        article(2, "现场信息显示事故中有5人受伤。", "来源乙", "https://source-b.local/2"),
        article(3, "另一来源称事故造成5人受伤。", "来源丙", "https://source-c.local/3"),
    ]
    result = VerificationService().verify(event(items), 1)

    assert result.overall_verdict == "contradicted"
    assert result.credibility_assessment.risk_score >= 75


def test_insufficient_and_high_language_text_have_cautious_narratives() -> None:
    items = [article(1, "原因已经百分百确定，惊天内幕。", "未知来源", "https://example.com/1")]
    result = VerificationService().verify(event(items), 1)
    summary = result.credibility_assessment.summary

    assert result.overall_verdict in {"insufficient_evidence", "not_verifiable"}
    assert all(word not in summary for word in ("可信", "事实已确认", "基本属实", "文章为假"))
    assert "证据不足不等于文章已经被证明为虚假" in summary


def test_assessment_confidence_drops_for_single_unknown_low_coverage_input() -> None:
    single = VerificationService().verify(
        event([article(1, "事故造成3人受伤。", "未知来源", "https://example.com/1")]),
        1,
    )
    multiple = VerificationService().verify(
        event(
            [
                article(1, "事故造成3人受伤。", "来源甲", "https://a.local/1"),
                article(2, "事故造成3人受伤。", "来源乙", "https://b.local/2"),
                article(3, "事故造成3人受伤。", "来源丙", "https://c.local/3"),
            ]
        ),
        1,
    )

    assert single.credibility_assessment.assessment_confidence < multiple.credibility_assessment.assessment_confidence


def test_assessment_is_stable_across_repeated_runs() -> None:
    items = [
        article(1, "事故造成3人受伤。", "来源甲", "https://a.local/1", title="惊天内幕"),
        article(2, "事故造成3人受伤。", "来源乙", "https://b.local/2"),
        article(3, "事故造成3人受伤。", "来源丙", "https://c.local/3"),
    ]
    service = VerificationService()

    assert service.verify(event(items), 1).credibility_assessment == service.verify(event(items), 1).credibility_assessment
