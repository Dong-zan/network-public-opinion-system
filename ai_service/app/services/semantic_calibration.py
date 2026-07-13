import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.event import Article
from app.schemas.verification import VerificationResponse
from app.schemas.verification_semantic import SemanticLLMOutput
from app.schemas.verification_semantic_calibration import (
    CalibrationRoleExpectation,
    CalibrationTypeMetrics,
    SavedSemanticOutputBundle,
    SemanticCalibrationCase,
    SemanticCalibrationFixture,
    SemanticCalibrationReport,
)
from app.services.semantic_credibility import (
    SemanticAnalysisContext,
    SemanticCredibilityValidator,
)


def safe_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def load_calibration_fixture(path: str | Path) -> SemanticCalibrationFixture:
    return SemanticCalibrationFixture.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_saved_outputs(path: str | Path) -> dict[str, dict[str, Any]]:
    bundle = SavedSemanticOutputBundle.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return {item.case_id: item.output for item in bundle.outputs}


def build_calibration_context(case: SemanticCalibrationCase) -> SemanticAnalysisContext:
    metadata = case.source_metadata
    target = Article(
        news_id=metadata.news_id,
        title=case.target_title,
        content=case.target_content,
        source=metadata.source,
        url=metadata.url,
        platform=metadata.platform,
        is_official=metadata.is_official,
        account_type=metadata.account_type,
        source_type=metadata.source_type,
        author=metadata.author,
    )
    articles = [target]
    seen_news_ids = {str(metadata.news_id)}
    for result in case.claim_results:
        for evidence in [*result.evidence, *result.context_evidence]:
            key = str(evidence.news_id)
            if key in seen_news_ids:
                continue
            seen_news_ids.add(key)
            articles.append(
                Article(
                    news_id=evidence.news_id,
                    title="校准证据",
                    content=evidence.quote,
                    source=evidence.source,
                    url=evidence.url,
                    platform="新闻网站",
                )
            )
    verification = VerificationResponse(
        target_news_id=metadata.news_id,
        overall_verdict="insufficient_evidence",
        evidence_score=0,
        claim_results=case.claim_results,
        score_explanation="离线语义校准上下文，不用于事实评分。",
    )
    return SemanticAnalysisContext(
        target_article=target,
        verification=verification,
        source_status="unknown",
        registered_source=False,
        domain_match=None,
        metadata_signals=(),
        deterministic_flags=(),
        article_max_chars=5000,
        articles=tuple(articles),
    )


def evaluate_calibration(
    fixture: SemanticCalibrationFixture,
    *,
    saved_outputs: dict[str, dict[str, Any]] | None = None,
) -> SemanticCalibrationReport:
    validator = SemanticCredibilityValidator()
    expected_by_type: dict[str, int] = {}
    accepted_by_type: dict[str, int] = {}
    true_positive_by_type: dict[str, int] = {}
    false_positive_by_type: dict[str, int] = {}
    false_negative_by_type: dict[str, int] = {}
    expected_flag_count = accepted_flag_count = 0
    true_positive = false_positive = false_negative = 0
    invalid_quote_count = invalid_evidence_reference_count = 0
    schema_failure_count = fallback_count = 0
    role_pass_count = role_case_count = 0
    failed_case_ids = []

    for case in fixture.cases:
        context = build_calibration_context(case)
        raw_output = case.candidate_output if saved_outputs is None else saved_outputs.get(case.case_id)
        expected = set(case.expected_flag_types)
        has_role_expectation = bool(case.expected_role_assessments or case.forbidden_role_assessments)
        role_case_count += int(has_role_expectation)
        expected_flag_count += len(expected)
        for flag_type in expected:
            expected_by_type[flag_type] = expected_by_type.get(flag_type, 0) + 1

        if raw_output is None:
            fallback_count += 1
            false_negative += len(expected)
            for flag_type in expected:
                false_negative_by_type[flag_type] = false_negative_by_type.get(flag_type, 0) + 1
            failed_case_ids.append(case.case_id)
            continue

        invalid_quote_count += _count_invalid_quotes(raw_output, context)
        invalid_evidence_reference_count += _count_invalid_evidence_references(raw_output, context)
        try:
            parsed = SemanticLLMOutput.model_validate(raw_output)
        except ValidationError:
            schema_failure_count += 1
            fallback_count += 1
            false_negative += len(expected)
            for flag_type in expected:
                false_negative_by_type[flag_type] = false_negative_by_type.get(flag_type, 0) + 1
            if expected:
                failed_case_ids.append(case.case_id)
            elif has_role_expectation:
                failed_case_ids.append(case.case_id)
            continue

        flags, roles = validator.validate(parsed, context)
        accepted = {flag.type for flag in flags}
        accepted_flag_count += len(accepted)
        for flag_type in accepted:
            accepted_by_type[flag_type] = accepted_by_type.get(flag_type, 0) + 1

        case_true_positive = expected & accepted
        case_false_positive = accepted - expected
        case_false_negative = expected - accepted
        true_positive += len(case_true_positive)
        false_positive += len(case_false_positive)
        false_negative += len(case_false_negative)
        for flag_type in case_true_positive:
            true_positive_by_type[flag_type] = true_positive_by_type.get(flag_type, 0) + 1
        for flag_type in case_false_positive:
            false_positive_by_type[flag_type] = false_positive_by_type.get(flag_type, 0) + 1
        for flag_type in case_false_negative:
            false_negative_by_type[flag_type] = false_negative_by_type.get(flag_type, 0) + 1

        role_passed = _roles_pass(case.expected_role_assessments, case.forbidden_role_assessments, roles)
        role_pass_count += int(role_passed and has_role_expectation)
        if case_false_positive or case_false_negative or not role_passed:
            failed_case_ids.append(case.case_id)

    all_types = sorted(set(expected_by_type) | set(accepted_by_type))
    per_flag_type = {}
    for flag_type in all_types:
        type_tp = true_positive_by_type.get(flag_type, 0)
        type_fp = false_positive_by_type.get(flag_type, 0)
        type_fn = false_negative_by_type.get(flag_type, 0)
        per_flag_type[flag_type] = CalibrationTypeMetrics(
            expected=expected_by_type.get(flag_type, 0),
            accepted=accepted_by_type.get(flag_type, 0),
            true_positive=type_tp,
            false_positive=type_fp,
            false_negative=type_fn,
            precision=safe_ratio(type_tp, type_tp + type_fp),
            recall=safe_ratio(type_tp, type_tp + type_fn),
        )

    precision = safe_ratio(true_positive, true_positive + false_positive)
    recall = safe_ratio(true_positive, true_positive + false_negative)
    return SemanticCalibrationReport(
        case_count=len(fixture.cases),
        expected_flag_count=expected_flag_count,
        accepted_flag_count=accepted_flag_count,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=safe_ratio(2 * true_positive, 2 * true_positive + false_positive + false_negative),
        per_flag_type=per_flag_type,
        role_assessment_pass_rate=safe_ratio(role_pass_count, role_case_count),
        invalid_quote_count=invalid_quote_count,
        invalid_evidence_reference_count=invalid_evidence_reference_count,
        schema_failure_count=schema_failure_count,
        fallback_count=fallback_count,
        failed_case_ids=sorted(set(failed_case_ids)),
    )


def _count_invalid_quotes(raw_output: dict[str, Any], context: SemanticAnalysisContext) -> int:
    target_text = context.target_article.title + "\n" + context.target_article.content
    count = 0
    for item in raw_output.get("language_flags", []):
        if isinstance(item, dict) and isinstance(item.get("quote"), str) and item["quote"] not in target_text:
            count += 1
    return count


def _count_invalid_evidence_references(raw_output: dict[str, Any], context: SemanticAnalysisContext) -> int:
    valid = {
        result.claim_id: {(item.quote, str(item.news_id)) for item in [*result.evidence, *result.context_evidence]}
        for result in context.verification.claim_results
    }
    count = 0
    for item in raw_output.get("language_flags", []):
        if not isinstance(item, dict):
            continue
        quote = item.get("evidence_quote")
        news_id = item.get("evidence_news_id")
        claim_id = item.get("related_claim_id")
        if quote is None and news_id is None:
            continue
        if claim_id not in valid or quote is None or news_id is None or (quote, str(news_id)) not in valid[claim_id]:
            count += 1
    return count


def _roles_pass(expected, forbidden, accepted) -> bool:
    accepted_keys = {_role_key(item) for item in accepted}
    expected_keys = {_role_key(item) for item in expected}
    forbidden_keys = {_role_key(item) for item in forbidden}
    return expected_keys <= accepted_keys and not (forbidden_keys & accepted_keys)


def _role_key(role: CalibrationRoleExpectation | Any) -> tuple[int, str, str]:
    return role.claim_id, role.publisher_role, role.attributed_role
