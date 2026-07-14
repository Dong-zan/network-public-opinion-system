import json
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import ValidationError

from app.schemas.event import Article
from app.schemas.verification import VerificationResponse
from app.schemas.verification_semantic import SemanticLLMOutput
from app.schemas.verification_semantic_calibration import (
    CalibrationRoleExpectation,
    CalibrationTypeMetrics,
    RepeatedSemanticCalibrationReport,
    RepeatedSemanticOutputBundle,
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


def load_repeated_outputs(path: str | Path) -> RepeatedSemanticOutputBundle:
    source = Path(path)
    paths = [source] if source.is_file() else sorted(source.glob("*.json"))
    bundles = []
    for candidate in paths:
        try:
            bundles.append(
                RepeatedSemanticOutputBundle.model_validate_json(
                    candidate.read_text(encoding="utf-8")
                )
            )
        except ValidationError:
            if source.is_file():
                raise
    if not bundles:
        raise ValueError("未找到合法的重复运行输出文件")
    metadata_items = [bundle.metadata for bundle in bundles]
    if any(item is None for item in metadata_items) and any(
        item is not None for item in metadata_items
    ):
        raise ValueError("重复运行输出包含不兼容的实验元数据")
    metadata = metadata_items[0]
    if metadata is not None:
        identity = metadata.model_dump(exclude={"created_at", "code_commit"})
        if any(
            item is None
            or item.model_dump(exclude={"created_at", "code_commit"}) != identity
            for item in metadata_items[1:]
        ):
            raise ValueError("重复运行输出来自不同实验，不能合并评测")
    providers = {bundle.provider for bundle in bundles}
    models = {bundle.model for bundle in bundles}
    return RepeatedSemanticOutputBundle(
        version=bundles[0].version,
        provider=next(iter(providers)) if len(providers) == 1 else "multiple",
        model=next(iter(models)) if len(models) == 1 else "multiple",
        created_at=min(bundle.created_at for bundle in bundles),
        metadata=metadata,
        runs=[run for bundle in bundles for run in bundle.runs],
    )


def build_calibration_context(
    case: SemanticCalibrationCase,
    *,
    article_max_chars: int = 5000,
) -> SemanticAnalysisContext:
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
        article_max_chars=max(1, article_max_chars),
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


def evaluate_repeated_calibration(
    fixture: SemanticCalibrationFixture,
    bundle: RepeatedSemanticOutputBundle,
) -> RepeatedSemanticCalibrationReport:
    validator = SemanticCredibilityValidator()
    cases = {case.case_id: case for case in fixture.cases}
    expected_by_type: dict[str, int] = {}
    accepted_by_type: dict[str, int] = {}
    true_positive_by_type: dict[str, int] = {}
    false_positive_by_type: dict[str, int] = {}
    false_negative_by_type: dict[str, int] = {}
    expected_flag_count = accepted_flag_count = 0
    true_positive = false_positive = false_negative = 0
    success_count = invalid_json_count = empty_output_count = provider_failure_count = 0
    schema_failure_count = fallback_count = 0
    invalid_quote_count = invalid_evidence_reference_count = invalid_claim_id_count = 0
    rejected_candidate_count = 0
    role_pass_count = role_case_count = 0
    neutral_run_count = neutral_false_positive_count = 0
    failed_case_ids = []
    flag_sets_by_case: dict[str, list[frozenset[str]]] = {}
    role_sets_by_case: dict[str, list[frozenset[tuple[int, str, str]]]] = {}
    latencies = []

    for run in bundle.runs:
        latencies.append(run.latency_ms)
        case = cases.get(run.case_id)
        if case is None:
            fallback_count += 1
            failed_case_ids.append(run.case_id)
            continue
        expected = set(case.expected_flag_types)
        expected_flag_count += len(expected)
        for flag_type in expected:
            expected_by_type[flag_type] = expected_by_type.get(flag_type, 0) + 1
        has_role_expectation = bool(case.expected_role_assessments or case.forbidden_role_assessments)
        role_case_count += int(has_role_expectation)

        if run.status != "success":
            fallback_count += 1
            if run.error_type == "invalid_json":
                invalid_json_count += 1
            elif run.error_type == "empty_output":
                empty_output_count += 1
            elif run.error_type == "schema_validation_error":
                schema_failure_count += 1
            elif run.error_type in {
                "provider_timeout",
                "provider_connection_error",
                "unknown_provider_error",
            }:
                provider_failure_count += 1
            false_negative += len(expected)
            for flag_type in expected:
                false_negative_by_type[flag_type] = false_negative_by_type.get(flag_type, 0) + 1
            failed_case_ids.append(case.case_id)
            continue

        success_count += 1
        parsed = run.parsed_output
        if parsed is None:
            fallback_count += 1
            failed_case_ids.append(case.case_id)
            continue
        context = build_calibration_context(case)
        raw_payload = parsed.model_dump(mode="json")
        invalid_quote_count += _count_invalid_quotes(raw_payload, context)
        invalid_evidence_reference_count += _count_invalid_evidence_references(raw_payload, context)
        invalid_claim_id_count += _count_invalid_claim_ids(raw_payload, context)
        flags, roles = validator.validate(parsed, context)
        rejected_candidate_count += len(parsed.language_flags) + len(parsed.source_role_assessments) - len(flags) - len(roles)
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
        if not expected:
            neutral_run_count += 1
            neutral_false_positive_count += int(bool(accepted))
        if case_false_positive or case_false_negative or not role_passed:
            failed_case_ids.append(case.case_id)

        flag_sets_by_case.setdefault(case.case_id, []).append(frozenset(accepted))
        role_sets_by_case.setdefault(case.case_id, []).append(
            frozenset(_role_key(role) for role in roles)
        )

    all_types = sorted(set(expected_by_type) | set(accepted_by_type))
    per_flag_type = _per_type_metrics(
        all_types,
        expected_by_type,
        accepted_by_type,
        true_positive_by_type,
        false_positive_by_type,
        false_negative_by_type,
    )
    per_case_consistency = {
        case_id: _average_pairwise_jaccard(values)
        for case_id, values in sorted(flag_sets_by_case.items())
    }
    repeated_flag_cases = {case_id: values for case_id, values in flag_sets_by_case.items() if len(values) >= 2}
    exact_agreements = [float(all(value == values[0] for value in values)) for values in repeated_flag_cases.values()]
    repeated_role_cases = [values for values in role_sets_by_case.values() if len(values) >= 2]
    per_flag_consistency = _per_flag_detection_consistency(cases, flag_sets_by_case)
    precision = safe_ratio(true_positive, true_positive + false_positive)
    recall = safe_ratio(true_positive, true_positive + false_negative)
    run_count = len(bundle.runs)
    return RepeatedSemanticCalibrationReport(
        metadata=bundle.metadata,
        case_count=len({run.case_id for run in bundle.runs if run.case_id in cases}),
        run_count=run_count,
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
        success_count=success_count,
        invalid_json_count=invalid_json_count,
        empty_output_count=empty_output_count,
        provider_failure_count=provider_failure_count,
        success_rate=safe_ratio(success_count, run_count),
        fallback_rate=safe_ratio(fallback_count, run_count),
        invalid_claim_id_count=invalid_claim_id_count,
        rejected_candidate_count=rejected_candidate_count,
        neutral_case_false_positive_rate=safe_ratio(neutral_false_positive_count, neutral_run_count),
        exact_flag_set_agreement_rate=round(mean(exact_agreements), 4) if exact_agreements else 0.0,
        average_flag_set_jaccard=(
            round(mean(_average_pairwise_jaccard(values) for values in repeated_flag_cases.values()), 4)
            if repeated_flag_cases
            else 0.0
        ),
        per_case_flag_set_consistency=per_case_consistency,
        per_flag_type_detection_consistency=per_flag_consistency,
        role_assessment_consistency=(
            round(mean(_average_pairwise_jaccard(values) for values in repeated_role_cases), 4)
            if repeated_role_cases
            else 0.0
        ),
        latency_count=len(latencies),
        latency_mean_ms=round(mean(latencies), 2) if latencies else 0.0,
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        latency_max_ms=round(max(latencies), 2) if latencies else 0.0,
    )


def _per_type_metrics(
    flag_types,
    expected_by_type,
    accepted_by_type,
    true_positive_by_type,
    false_positive_by_type,
    false_negative_by_type,
):
    result = {}
    for flag_type in flag_types:
        true_positive = true_positive_by_type.get(flag_type, 0)
        false_positive = false_positive_by_type.get(flag_type, 0)
        false_negative = false_negative_by_type.get(flag_type, 0)
        result[flag_type] = CalibrationTypeMetrics(
            expected=expected_by_type.get(flag_type, 0),
            accepted=accepted_by_type.get(flag_type, 0),
            true_positive=true_positive,
            false_positive=false_positive,
            false_negative=false_negative,
            precision=safe_ratio(true_positive, true_positive + false_positive),
            recall=safe_ratio(true_positive, true_positive + false_negative),
        )
    return result


def flag_set_jaccard(first: set | frozenset, second: set | frozenset) -> float:
    if not first and not second:
        return 1.0
    return safe_ratio(len(first & second), len(first | second))


def _average_pairwise_jaccard(values) -> float:
    if len(values) < 2:
        return 1.0 if values else 0.0
    return round(mean(flag_set_jaccard(first, second) for first, second in combinations(values, 2)), 4)


def _per_flag_detection_consistency(cases, values_by_case) -> dict[str, float]:
    flag_types = sorted(
        {flag_type for case in cases.values() for flag_type in case.expected_flag_types}
        | {flag_type for values in values_by_case.values() for value in values for flag_type in value}
    )
    result = {}
    for flag_type in flag_types:
        rates = []
        for case_id, values in values_by_case.items():
            if flag_type not in cases[case_id].expected_flag_types and not any(flag_type in value for value in values):
                continue
            rates.append(safe_ratio(sum(flag_type in value for value in values), len(values)))
        result[flag_type] = round(mean(rates), 4) if rates else 0.0
    return result


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


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


def _count_invalid_claim_ids(raw_output: dict[str, Any], context: SemanticAnalysisContext) -> int:
    valid_claim_ids = {result.claim_id for result in context.verification.claim_results}
    count = 0
    for item in raw_output.get("language_flags", []):
        if isinstance(item, dict) and item.get("related_claim_id") is not None and item["related_claim_id"] not in valid_claim_ids:
            count += 1
    for item in raw_output.get("source_role_assessments", []):
        if isinstance(item, dict) and item.get("claim_id") not in valid_claim_ids:
            count += 1
    return count


def _roles_pass(expected, forbidden, accepted) -> bool:
    accepted_keys = {_role_key(item) for item in accepted}
    expected_keys = {_role_key(item) for item in expected}
    forbidden_keys = {_role_key(item) for item in forbidden}
    return expected_keys <= accepted_keys and not (forbidden_keys & accepted_keys)


def _role_key(role: CalibrationRoleExpectation | Any) -> tuple[int, str, str]:
    return role.claim_id, role.publisher_role, role.attributed_role
