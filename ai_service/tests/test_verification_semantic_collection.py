import hashlib
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.llm.base import LLMProvider
from app.llm.prompt_types import PromptBundle
from app.schemas.verification_semantic import SemanticLLMOutput
from app.schemas.verification_semantic_calibration import (
    REPEATED_SEMANTIC_COLLECTION_SCHEMA_VERSION,
    RepeatedSemanticOutputBundle,
    RepeatedSemanticRun,
)
from app.services.semantic_calibration import (
    evaluate_repeated_calibration,
    flag_set_jaccard,
    load_calibration_fixture,
)
from app.services.semantic_output_collection import collect_semantic_outputs
from app.services import semantic_output_collection
from scripts import collect_verification_semantic_outputs as collector_script


FIXTURE_PATH = "tests/fixtures/verification_semantic_calibration.json"


class StubProvider(LLMProvider):
    name = "stub"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def generate(self, prompt: PromptBundle) -> str:
        self.calls += 1
        output = self.outputs[min(self.calls - 1, len(self.outputs) - 1)]
        if isinstance(output, Exception):
            raise output
        return output


def _raw(output: dict) -> str:
    return json.dumps(output, ensure_ascii=False)


def _bundle(runs) -> RepeatedSemanticOutputBundle:
    return RepeatedSemanticOutputBundle(
        provider="stub",
        model="stub-model",
        created_at=datetime.now(timezone.utc),
        runs=runs,
    )


def _success_run(case_id: str, run_id: str, output: dict, latency: float):
    parsed = SemanticLLMOutput.model_validate(output)
    return RepeatedSemanticRun(
        case_id=case_id,
        run_id=run_id,
        status="success",
        latency_ms=latency,
        raw_output=_raw(output),
        parsed_output=parsed,
    )


def test_collector_without_allow_network_never_creates_provider_or_socket(monkeypatch) -> None:
    def fail_provider():
        raise AssertionError("未授权时不得创建Provider")

    def fail_network(*args, **kwargs):
        raise AssertionError("未授权时不得访问网络")

    def fail_env_file(*args, **kwargs):
        raise AssertionError("未授权时不得读取env文件")

    monkeypatch.setattr(collector_script, "_create_authorized_provider", fail_provider)
    monkeypatch.setattr(collector_script, "_load_environment_file", fail_env_file)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    assert collector_script.main(["--max-cases", "1", "--env-file", "never-read.env"]) == 2


def test_authorized_env_file_is_loaded_before_settings(monkeypatch, tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    order = []
    captured = {}

    monkeypatch.setattr(
        collector_script,
        "_load_environment_file",
        lambda value: order.append(("env", value)),
    )

    def create_provider():
        order.append(("settings-and-provider", None))
        return StubProvider([_raw(fixture.cases[0].candidate_output)]), "stub", "actual-model", 5000, 1000, 0.2, False

    monkeypatch.setattr(collector_script, "_create_authorized_provider", create_provider)
    monkeypatch.setattr(collector_script, "_safe_output_directory", lambda value: tmp_path)
    monkeypatch.setattr(collector_script, "_safe_git_commit", lambda: None)
    monkeypatch.setattr(
        collector_script,
        "collect_semantic_outputs",
        lambda **kwargs: captured.update(kwargs),
    )

    result = collector_script.main(
        ["--allow-network", "--env-file", "explicit.env", "--fixture", FIXTURE_PATH]
    )

    assert result == 0
    assert order == [("env", "explicit.env"), ("settings-and-provider", None)]
    assert captured["model_name"] == "actual-model"


def test_explicit_env_loader_reads_only_supplied_file(monkeypatch, tmp_path) -> None:
    marker = "A3_1_TEST_ENV_MARKER"
    env_path = tmp_path / "calibration.env"
    env_path.write_text(f"{marker}=loaded-from-explicit-file\n", encoding="utf-8")
    monkeypatch.delenv(marker, raising=False)

    collector_script._load_environment_file(str(env_path))

    assert os.environ[marker] == "loaded-from-explicit-file"


def test_missing_env_file_fails_before_provider_creation(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        collector_script,
        "_create_authorized_provider",
        lambda: (_ for _ in ()).throw(AssertionError("不得创建Provider")),
    )

    result = collector_script.main(
        ["--allow-network", "--env-file", str(tmp_path / "missing.env")]
    )

    assert result == 2


def test_repeat_three_creates_unique_run_ids(tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    output = _raw(fixture.cases[0].candidate_output)
    provider = StubProvider([output])

    bundle = collect_semantic_outputs(
        provider=provider,
        provider_name="stub",
        model_name="stub-model",
        fixture=fixture,
        output_path=tmp_path / "runs.json",
        repeat=3,
        max_cases=1,
    )

    assert provider.calls == 3
    assert [run.run_id for run in bundle.runs] == ["run-1", "run-2", "run-3"]
    assert len({(run.case_id, run.run_id) for run in bundle.runs}) == 3


def test_duplicate_case_and_run_id_is_rejected() -> None:
    output = SemanticLLMOutput(language_flags=[], source_role_assessments=[])
    run = RepeatedSemanticRun(
        case_id="c01",
        run_id="run-1",
        status="success",
        latency_ms=1,
        parsed_output=output,
    )

    with pytest.raises(ValidationError):
        _bundle([run, run])


def test_resume_skips_completed_runs(tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    output = _raw(fixture.cases[0].candidate_output)
    output_path = tmp_path / "runs.json"
    first_provider = StubProvider([output])
    collect_semantic_outputs(
        provider=first_provider,
        provider_name="stub",
        model_name="stub-model",
        fixture=fixture,
        output_path=output_path,
        repeat=2,
        max_cases=1,
    )
    resumed_provider = StubProvider([output])

    resumed = collect_semantic_outputs(
        provider=resumed_provider,
        provider_name="stub",
        model_name="stub-model",
        fixture=fixture,
        output_path=output_path,
        repeat=2,
        max_cases=1,
        resume=True,
    )

    assert first_provider.calls == 2
    assert resumed_provider.calls == 0
    assert len(resumed.runs) == 2


def test_bundle_records_reproducible_experiment_metadata(tmp_path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_bytes = (Path(FIXTURE_PATH)).read_bytes()
    fixture_path.write_bytes(fixture_bytes)
    fixture = load_calibration_fixture(fixture_path)
    expected_sha = hashlib.sha256(fixture_bytes).hexdigest()
    provider = StubProvider([_raw(fixture.cases[0].candidate_output)])

    bundle = collect_semantic_outputs(
        provider=provider,
        provider_name="stub",
        model_name="actual-model",
        fixture=fixture,
        fixture_sha256=expected_sha,
        output_path=tmp_path / "runs.json",
        max_cases=1,
        run_label="experiment-a",
        article_max_chars=4321,
        max_tokens=2048,
        temperature=0.1,
        thinking_enabled=False,
        code_commit="a" * 40,
    )

    assert bundle.metadata is not None
    assert bundle.metadata.fixture_version == fixture.version
    assert bundle.metadata.fixture_sha256 == expected_sha
    assert bundle.metadata.prompt_version == semantic_output_collection.VERIFICATION_SEMANTIC_PROMPT_VERSION
    assert bundle.metadata.validator_version == semantic_output_collection.SEMANTIC_CREDIBILITY_VALIDATOR_VERSION
    assert bundle.metadata.collection_schema_version == REPEATED_SEMANTIC_COLLECTION_SCHEMA_VERSION
    assert bundle.metadata.actual_model == "actual-model"
    assert bundle.metadata.run_label == "experiment-a"
    assert bundle.metadata.article_max_chars == 4321
    assert bundle.metadata.max_tokens == 2048
    assert bundle.metadata.temperature == 0.1
    assert bundle.metadata.thinking_enabled is False
    assert bundle.metadata.code_commit == "a" * 40


def test_model_label_is_run_label_not_actual_model(monkeypatch, tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    captured = {}
    monkeypatch.setattr(collector_script, "_safe_output_directory", lambda value: tmp_path)
    monkeypatch.setattr(collector_script, "_safe_git_commit", lambda: None)
    monkeypatch.setattr(
        collector_script,
        "_create_authorized_provider",
        lambda: (
            StubProvider([_raw(fixture.cases[0].candidate_output)]),
            "stub",
            "real-configured-model",
            5000,
            3000,
            0.2,
            False,
        ),
    )
    monkeypatch.setattr(
        collector_script,
        "collect_semantic_outputs",
        lambda **kwargs: captured.update(kwargs),
    )

    result = collector_script.main(
        [
            "--allow-network",
            "--fixture",
            FIXTURE_PATH,
            "--model-label",
            "display-only-label",
        ]
    )

    assert result == 0
    assert captured["model_name"] == "real-configured-model"
    assert captured["run_label"] == "display-only-label"


def test_unknown_case_id_is_rejected_before_provider_call(tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    provider = StubProvider([_raw(fixture.cases[0].candidate_output)])

    with pytest.raises(ValueError, match="fixture中不存在case_id"):
        collect_semantic_outputs(
            provider=provider,
            provider_name="stub",
            model_name="stub-model",
            fixture=fixture,
            output_path=tmp_path / "runs.json",
            case_ids={"missing-case"},
        )

    assert provider.calls == 0
    assert not (tmp_path / "runs.json").exists()


def _collect_for_resume(
    *,
    tmp_path,
    fixture,
    output_path,
    resume=False,
    provider_name="stub",
    model_name="stub-model",
    fixture_sha256="a" * 64,
    article_max_chars=5000,
    max_tokens=3000,
    temperature=0.2,
    thinking_enabled=False,
):
    return collect_semantic_outputs(
        provider=StubProvider([_raw(fixture.cases[0].candidate_output)]),
        provider_name=provider_name,
        model_name=model_name,
        fixture=fixture,
        fixture_sha256=fixture_sha256,
        output_path=output_path,
        max_cases=1,
        resume=resume,
        article_max_chars=article_max_chars,
        max_tokens=max_tokens,
        temperature=temperature,
        thinking_enabled=thinking_enabled,
    )


@pytest.mark.parametrize(
    ("changed", "expected_field"),
    [
        ({"model_name": "different-model"}, "actual_model"),
        ({"provider_name": "different-provider"}, "provider"),
        ({"fixture_sha256": "b" * 64}, "fixture_sha256"),
        ({"article_max_chars": 4999}, "article_max_chars"),
        ({"max_tokens": 2048}, "max_tokens"),
        ({"temperature": 0.3}, "temperature"),
        ({"thinking_enabled": True, "temperature": None}, "thinking_enabled"),
    ],
)
def test_resume_rejects_incompatible_experiment_metadata(
    tmp_path,
    changed,
    expected_field,
) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    output_path = tmp_path / "runs.json"
    _collect_for_resume(
        tmp_path=tmp_path,
        fixture=fixture,
        output_path=output_path,
    )

    with pytest.raises(ValueError, match=expected_field):
        _collect_for_resume(
            tmp_path=tmp_path,
            fixture=fixture,
            output_path=output_path,
            resume=True,
            **changed,
        )


def test_resume_rejects_fixture_version_change(tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    output_path = tmp_path / "runs.json"
    _collect_for_resume(tmp_path=tmp_path, fixture=fixture, output_path=output_path)
    changed_fixture = fixture.model_copy(update={"version": fixture.version + "-changed"})

    with pytest.raises(ValueError, match="fixture_version"):
        _collect_for_resume(
            tmp_path=tmp_path,
            fixture=changed_fixture,
            output_path=output_path,
            resume=True,
        )


def test_resume_rejects_prompt_or_validator_version_change(monkeypatch, tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    prompt_path = tmp_path / "prompt-runs.json"
    _collect_for_resume(tmp_path=tmp_path, fixture=fixture, output_path=prompt_path)
    monkeypatch.setattr(
        semantic_output_collection,
        "VERIFICATION_SEMANTIC_PROMPT_VERSION",
        "changed-prompt-version",
    )
    with pytest.raises(ValueError, match="prompt_version"):
        _collect_for_resume(
            tmp_path=tmp_path,
            fixture=fixture,
            output_path=prompt_path,
            resume=True,
        )

    monkeypatch.undo()
    validator_path = tmp_path / "validator-runs.json"
    _collect_for_resume(tmp_path=tmp_path, fixture=fixture, output_path=validator_path)
    monkeypatch.setattr(
        semantic_output_collection,
        "SEMANTIC_CREDIBILITY_VALIDATOR_VERSION",
        "changed-validator-version",
    )
    with pytest.raises(ValueError, match="validator_version"):
        _collect_for_resume(
            tmp_path=tmp_path,
            fixture=fixture,
            output_path=validator_path,
            resume=True,
        )


def test_resume_rejects_collection_schema_version_change(monkeypatch, tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    output_path = tmp_path / "runs.json"
    _collect_for_resume(tmp_path=tmp_path, fixture=fixture, output_path=output_path)
    monkeypatch.setattr(
        semantic_output_collection,
        "REPEATED_SEMANTIC_COLLECTION_SCHEMA_VERSION",
        "incompatible-schema-version",
    )

    with pytest.raises(ValueError, match="collection_schema_version"):
        _collect_for_resume(
            tmp_path=tmp_path,
            fixture=fixture,
            output_path=output_path,
            resume=True,
        )


def test_corrupted_resume_bundle_is_not_overwritten(tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    output_path = tmp_path / "runs.json"
    original = b'{"broken":'
    output_path.write_bytes(original)

    with pytest.raises(ValidationError):
        _collect_for_resume(
            tmp_path=tmp_path,
            fixture=fixture,
            output_path=output_path,
            resume=True,
        )

    assert output_path.read_bytes() == original


@pytest.mark.parametrize(
    ("provider_output", "error_type"),
    [
        (TimeoutError("private timeout detail"), "provider_timeout"),
        (ConnectionError("private connection detail"), "provider_connection_error"),
        ("", "empty_output"),
        ("not-json", "invalid_json"),
        (_raw({"language_flags": [], "source_role_assessments": [], "risk_score": 99}), "schema_validation_error"),
    ],
)
def test_collection_records_safe_failure_categories(tmp_path, provider_output, error_type) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    bundle = collect_semantic_outputs(
        provider=StubProvider([provider_output]),
        provider_name="stub",
        model_name="stub-model",
        fixture=fixture,
        output_path=tmp_path / "runs.json",
        max_cases=1,
    )

    assert bundle.runs[0].status == "failed"
    assert bundle.runs[0].error_type == error_type


def test_validator_rejects_illegal_quote_in_collected_success(tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    case = next(item for item in fixture.cases if item.case_id == "c26-fabricated-target-quote")
    provider = StubProvider([_raw(case.candidate_output)])

    bundle = collect_semantic_outputs(
        provider=provider,
        provider_name="stub",
        model_name="stub-model",
        fixture=fixture,
        output_path=tmp_path / "runs.json",
        case_ids={case.case_id},
    )
    report = evaluate_repeated_calibration(fixture, bundle)

    assert bundle.runs[0].status == "success"
    assert report.accepted_flag_count == 0
    assert report.invalid_quote_count == 1
    assert report.rejected_candidate_count == 1


def test_collection_output_and_logs_do_not_leak_exception_or_prompt(tmp_path, caplog) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    secret = "testing-api-key Authorization: Bearer private"

    with caplog.at_level("INFO"):
        collect_semantic_outputs(
            provider=StubProvider([RuntimeError(secret)]),
            provider_name="stub",
            model_name="stub-model",
            fixture=fixture,
            output_path=tmp_path / "runs.json",
            max_cases=1,
        )

    saved = (tmp_path / "runs.json").read_text(encoding="utf-8")
    assert secret not in saved
    assert "Authorization" not in saved
    assert secret not in caplog.text
    assert fixture.cases[0].target_content not in caplog.text
    assert "<untrusted_target_article>" not in caplog.text


def test_collection_metadata_does_not_capture_environment_secrets(monkeypatch, tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    secret = "a3-test-api-key"
    environment_marker = "private-env-value"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    monkeypatch.setenv("A3_PRIVATE_ENV", environment_marker)

    collect_semantic_outputs(
        provider=StubProvider([_raw(fixture.cases[0].candidate_output)]),
        provider_name="stub",
        model_name="stub-model",
        fixture=fixture,
        output_path=tmp_path / "runs.json",
        max_cases=1,
    )

    saved = (tmp_path / "runs.json").read_text(encoding="utf-8")
    assert secret not in saved
    assert environment_marker not in saved
    assert "DEEPSEEK_API_KEY" not in saved


def test_repeated_evaluator_metrics_stability_and_latency() -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    case = next(item for item in fixture.cases if item.case_id == "c02-finalized-exaggeration")
    accepted = case.candidate_output
    empty = {"language_flags": [], "source_role_assessments": []}
    bundle = _bundle(
        [
            _success_run(case.case_id, "run-1", accepted, 100),
            _success_run(case.case_id, "run-2", accepted, 200),
            _success_run(case.case_id, "run-3", empty, 300),
        ]
    )

    report = evaluate_repeated_calibration(fixture, bundle)

    assert report.run_count == 3
    assert report.success_count == 3
    assert report.true_positive == 2
    assert report.false_positive == 0
    assert report.false_negative == 1
    assert report.precision == 1.0
    assert report.recall == pytest.approx(0.6667)
    assert report.f1 == 0.8
    assert report.exact_flag_set_agreement_rate == 0.0
    assert report.average_flag_set_jaccard == pytest.approx(0.3333)
    assert report.per_case_flag_set_consistency[case.case_id] == pytest.approx(0.3333)
    assert report.per_flag_type_detection_consistency["preliminary_as_confirmed"] == pytest.approx(0.6667)
    assert report.latency_count == 3
    assert report.latency_mean_ms == 200
    assert report.latency_p50_ms == 200
    assert report.latency_p95_ms == 290
    assert report.latency_max_ms == 300


def test_repeated_evaluator_exposes_experiment_identity(tmp_path) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    bundle = _collect_for_resume(
        tmp_path=tmp_path,
        fixture=fixture,
        output_path=tmp_path / "runs.json",
    )

    report = evaluate_repeated_calibration(fixture, bundle)

    assert report.metadata == bundle.metadata
    rendered = report.model_dump(mode="json")["metadata"]
    assert rendered["fixture_sha256"] == "a" * 64
    assert rendered["actual_model"] == "stub-model"
    assert rendered["prompt_version"]
    assert rendered["validator_version"]


def test_exact_agreement_jaccard_and_zero_denominators() -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    case = next(item for item in fixture.cases if item.case_id == "c02-finalized-exaggeration")
    bundle = _bundle(
        [
            _success_run(case.case_id, "run-1", case.candidate_output, 0),
            _success_run(case.case_id, "run-2", case.candidate_output, 0),
        ]
    )

    report = evaluate_repeated_calibration(fixture, bundle)
    empty_report = evaluate_repeated_calibration(fixture, _bundle([]))

    assert flag_set_jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3, abs=0.0001)
    assert flag_set_jaccard(set(), set()) == 1.0
    assert report.exact_flag_set_agreement_rate == 1.0
    assert report.average_flag_set_jaccard == 1.0
    assert empty_report.success_rate == 0.0
    assert empty_report.fallback_rate == 0.0
    assert empty_report.latency_p95_ms == 0.0
