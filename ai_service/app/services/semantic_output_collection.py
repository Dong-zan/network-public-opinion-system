import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.llm.base import LLMProvider
from app.llm.verification_semantic_prompts import (
    VERIFICATION_SEMANTIC_PROMPT_VERSION,
    build_verification_semantic_prompt,
)
from app.schemas.verification_semantic import SemanticLLMOutput
from app.schemas.verification_semantic_calibration import (
    CollectionErrorType,
    CalibrationRunMetadata,
    REPEATED_SEMANTIC_COLLECTION_SCHEMA_VERSION,
    RepeatedSemanticOutputBundle,
    RepeatedSemanticRun,
    SemanticCalibrationFixture,
)
from app.services.semantic_calibration import build_calibration_context
from app.services.semantic_credibility import (
    SEMANTIC_CREDIBILITY_VALIDATOR_VERSION,
    SemanticCredibilityValidator,
)


logger = logging.getLogger(__name__)

_RESUME_COMPATIBILITY_FIELDS = (
    "fixture_sha256",
    "fixture_version",
    "prompt_version",
    "validator_version",
    "provider",
    "actual_model",
    "run_label",
    "article_max_chars",
    "thinking_enabled",
    "temperature",
    "max_tokens",
    "collection_schema_version",
)


def collect_semantic_outputs(
    *,
    provider: LLMProvider,
    provider_name: str,
    model_name: str,
    fixture: SemanticCalibrationFixture,
    output_path: str | Path,
    repeat: int = 1,
    case_ids: set[str] | None = None,
    max_cases: int | None = None,
    delay_seconds: float = 0,
    resume: bool = False,
    article_max_chars: int = 5000,
    fixture_sha256: str | None = None,
    run_label: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    thinking_enabled: bool | None = None,
    code_commit: str | None = None,
) -> RepeatedSemanticOutputBundle:
    if repeat < 1:
        raise ValueError("repeat必须至少为1")
    if max_cases is not None and max_cases < 1:
        raise ValueError("max_cases必须至少为1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds不能为负数")

    available_case_ids = {case.case_id for case in fixture.cases}
    unknown_case_ids = sorted((case_ids or set()) - available_case_ids)
    if unknown_case_ids:
        raise ValueError("fixture中不存在case_id: " + ", ".join(unknown_case_ids))

    created_at = datetime.now(timezone.utc)
    metadata = CalibrationRunMetadata(
        fixture_version=fixture.version,
        fixture_sha256=fixture_sha256 or _canonical_fixture_sha256(fixture),
        prompt_version=VERIFICATION_SEMANTIC_PROMPT_VERSION,
        validator_version=SEMANTIC_CREDIBILITY_VALIDATOR_VERSION,
        provider=provider_name,
        actual_model=model_name,
        run_label=run_label,
        article_max_chars=article_max_chars,
        max_tokens=max_tokens,
        temperature=temperature,
        thinking_enabled=thinking_enabled,
        collection_schema_version=REPEATED_SEMANTIC_COLLECTION_SCHEMA_VERSION,
        created_at=created_at,
        code_commit=code_commit,
    )
    destination = Path(output_path)
    existing = _load_existing(destination) if resume and destination.exists() else None
    if existing is not None:
        _validate_resume_metadata(existing.metadata, metadata)
    bundle = existing or RepeatedSemanticOutputBundle(
        provider=provider_name,
        model=model_name,
        created_at=created_at,
        metadata=metadata,
        runs=[],
    )
    completed = {(item.case_id, item.run_id) for item in bundle.runs}
    selected_cases = [case for case in fixture.cases if case_ids is None or case.case_id in case_ids]
    if max_cases is not None:
        selected_cases = selected_cases[:max_cases]

    validator = SemanticCredibilityValidator()
    pending_count = sum(
        (case.case_id, f"run-{index}") not in completed
        for case in selected_cases
        for index in range(1, repeat + 1)
    )
    executed = 0
    for case in selected_cases:
        context = build_calibration_context(case, article_max_chars=article_max_chars)
        for index in range(1, repeat + 1):
            run_id = f"run-{index}"
            if (case.case_id, run_id) in completed:
                continue
            if executed and delay_seconds:
                time.sleep(delay_seconds)
            executed += 1
            logger.info(
                "semantic_collection_started case_id=%s run_id=%s provider=%s model=%s started_at=%s",
                case.case_id,
                run_id,
                provider_name,
                model_name,
                datetime.now(timezone.utc).isoformat(),
            )
            started = time.perf_counter()
            raw_output = None
            parse_status = "not_run"
            validation_status = "not_run"
            try:
                prompt = build_verification_semantic_prompt(context)
                raw_output = provider.generate(prompt)
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                if not isinstance(raw_output, str) or not raw_output.strip():
                    run = _failed_run(case.case_id, run_id, latency_ms, "empty_output")
                    parse_status = "empty_output"
                else:
                    try:
                        decoded = json.loads(raw_output)
                    except json.JSONDecodeError:
                        run = _failed_run(case.case_id, run_id, latency_ms, "invalid_json", raw_output)
                        parse_status = "invalid_json"
                    else:
                        try:
                            parsed = SemanticLLMOutput.model_validate(decoded)
                        except ValidationError:
                            run = _failed_run(
                                case.case_id,
                                run_id,
                                latency_ms,
                                "schema_validation_error",
                                raw_output,
                            )
                            parse_status = "schema_validation_error"
                        else:
                            validator.validate(parsed, context)
                            run = RepeatedSemanticRun(
                                case_id=case.case_id,
                                run_id=run_id,
                                status="success",
                                latency_ms=latency_ms,
                                raw_output=raw_output,
                                parsed_output=parsed,
                            )
                            parse_status = "success"
                            validation_status = "passed"
            except Exception as exc:
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                error_type = classify_collection_error(exc)
                run = _failed_run(case.case_id, run_id, latency_ms, error_type)
                parse_status = error_type

            bundle = bundle.model_copy(update={"runs": [*bundle.runs, run]})
            _save_bundle(destination, bundle)
            logger.info(
                "semantic_collection_completed case_id=%s run_id=%s provider=%s model=%s finished_at=%s "
                "latency_ms=%s response_chars=%s parse_status=%s validation_status=%s error_type=%s fallback=%s",
                case.case_id,
                run_id,
                provider_name,
                model_name,
                datetime.now(timezone.utc).isoformat(),
                run.latency_ms,
                len(raw_output) if isinstance(raw_output, str) else 0,
                parse_status,
                validation_status,
                run.error_type,
                run.status != "success",
            )
    if pending_count == 0:
        _save_bundle(destination, bundle)
    return bundle


def classify_collection_error(exc: Exception) -> CollectionErrorType:
    diagnostic = getattr(exc, "diagnostic_category", None)
    if isinstance(exc, TimeoutError) or diagnostic == "provider_timeout":
        return "provider_timeout"
    if isinstance(exc, ConnectionError) or diagnostic in {"provider_connection", "provider_connection_error"}:
        return "provider_connection_error"
    return "unknown_provider_error"


def _failed_run(
    case_id: str,
    run_id: str,
    latency_ms: float,
    error_type: CollectionErrorType,
    raw_output: str | None = None,
) -> RepeatedSemanticRun:
    return RepeatedSemanticRun(
        case_id=case_id,
        run_id=run_id,
        status="failed",
        latency_ms=latency_ms,
        raw_output=raw_output,
        error_type=error_type,
    )


def _load_existing(path: Path) -> RepeatedSemanticOutputBundle:
    return RepeatedSemanticOutputBundle.model_validate_json(path.read_text(encoding="utf-8"))


def _canonical_fixture_sha256(fixture: SemanticCalibrationFixture) -> str:
    canonical = json.dumps(
        fixture.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_resume_metadata(
    existing: CalibrationRunMetadata | None,
    current: CalibrationRunMetadata,
) -> None:
    if existing is None:
        raise ValueError(
            "resume不兼容字段: metadata；旧采集文件缺少实验身份，请使用新的output-dir"
        )
    incompatible = [
        field
        for field in _RESUME_COMPATIBILITY_FIELDS
        if getattr(existing, field) != getattr(current, field)
    ]
    if incompatible:
        raise ValueError(
            "resume不兼容字段: " + ", ".join(incompatible) + "；请使用新的output-dir"
        )


def _save_bundle(path: Path, bundle: RepeatedSemanticOutputBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
