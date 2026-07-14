import json
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.llm.verification_semantic_prompts import (
    SEMANTIC_SYSTEM_PROMPT,
    build_verification_semantic_prompt,
)
from app.schemas.event import Article
from app.schemas.verification import ClaimVerificationResult, VerificationResponse
from app.schemas.verification_semantic import SemanticLLMOutput
from app.schemas.verification_semantic_calibration import SemanticCalibrationFixture
from app.services.semantic_calibration import (
    build_calibration_context,
    evaluate_calibration,
    load_calibration_fixture,
    load_saved_outputs,
    safe_ratio,
)
from app.services.semantic_credibility import (
    SemanticAnalysisContext,
    SemanticCredibilityValidator,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "verification_semantic_calibration.json"


def _context(article: Article) -> SemanticAnalysisContext:
    verification = VerificationResponse(
        target_news_id=article.news_id or 1,
        overall_verdict="insufficient_evidence",
        evidence_score=0,
        claim_results=[
            ClaimVerificationResult(
                claim_id=1,
                claim="救援工作已经展开",
                verdict="insufficient_evidence",
                independent_source_count=0,
            )
        ],
        score_explanation="测试说明。",
    )
    return SemanticAnalysisContext(article, verification, "unknown", False, None, (), (), 5000, (article,))


def _role_output(publisher_role: str, attributed_role: str = "unknown", quote: str | None = None):
    role = {
        "claim_id": 1,
        "publisher_role": publisher_role,
        "attributed_role": attributed_role,
        "role_relevance": "medium",
        "explanation": "仅用于测试角色准入。",
    }
    if quote is not None:
        role["quote"] = quote
    return SemanticLLMOutput.model_validate(
        {"language_flags": [], "source_role_assessments": [role]}
    )


def test_calibration_fixture_loads_and_has_unique_cases() -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)

    assert len(fixture.cases) >= 30
    assert len({case.case_id for case in fixture.cases}) == len(fixture.cases)
    assert all(
        not (set(case.expected_flag_types) & set(case.forbidden_flag_types))
        for case in fixture.cases
    )


def test_calibration_fixture_rejects_duplicate_ids_and_conflicting_expectations() -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    payload = fixture.model_dump(mode="json")
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    with pytest.raises(ValidationError):
        SemanticCalibrationFixture.model_validate(payload)

    payload = fixture.model_dump(mode="json")
    payload["cases"][0]["expected_flag_types"] = ["preliminary_as_confirmed"]
    with pytest.raises(ValidationError):
        SemanticCalibrationFixture.model_validate(payload)


def test_fixture_validator_metrics_are_correct_and_precise() -> None:
    report = evaluate_calibration(load_calibration_fixture(FIXTURE_PATH))

    assert report.case_count == 30
    assert report.true_positive == report.expected_flag_count
    assert report.false_positive == 0
    assert report.false_negative == 0
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1 == 1.0
    assert report.role_assessment_pass_rate == 1.0
    assert report.invalid_quote_count >= 1
    assert report.invalid_evidence_reference_count >= 2
    assert report.schema_failure_count == 1


def test_empty_metric_denominators_are_safe() -> None:
    assert safe_ratio(0, 0) == 0.0
    assert safe_ratio(1, 0) == 0.0


def test_saved_output_mode_is_offline(tmp_path, monkeypatch) -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    saved_path = tmp_path / "saved-output.json"
    saved_path.write_text(
        json.dumps(
            {
                "outputs": [
                    {"case_id": case.case_id, "output": case.candidate_output}
                    for case in fixture.cases
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fail_network(*args, **kwargs):
        raise AssertionError("离线评测不得访问网络")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    report = evaluate_calibration(fixture, saved_outputs=load_saved_outputs(saved_path))

    assert report.case_count == 30
    assert report.precision == 1.0


def test_prompt_contains_complex_definitions_and_counterexamples() -> None:
    fixture = load_calibration_fixture(FIXTURE_PATH)
    prompt = build_verification_semantic_prompt(build_calibration_context(fixture.cases[0]))

    for flag_type in (
        "preliminary_as_confirmed",
        "uncertainty_removed",
        "title_body_mismatch",
        "unsupported_causality",
        "unsupported_generalization",
    ):
        assert flag_type in SEMANTIC_SYSTEM_PROMPT
    assert "完成率100%" in prompt.system_prompt
    assert "初步原因指向故障" in prompt.system_prompt
    assert "事故造成3人受伤" in prompt.system_prompt
    assert "强烈表达不代表文章必然虚假" in prompt.system_prompt
    assert "现场无明火、未发生燃烧" in prompt.system_prompt
    assert "百分百最终确定" in prompt.system_prompt
    assert "导致、由于、因而" in prompt.system_prompt
    assert "禁止输出空字符串" in prompt.system_prompt
    assert "publisher_metadata、attribution_quote、unknown" in prompt.system_prompt
    assert "不得根据“事故原因、调查、运营”等主题词猜测角色" in prompt.system_prompt


def test_official_enterprise_account_is_not_government_notice() -> None:
    article = Article(
        news_id=1,
        title="企业说明",
        content="公司表示救援工作已经展开。",
        platform="企业网站",
        is_official=True,
        account_type="企业官方账号",
        source_type="企业",
    )

    _, roles = SemanticCredibilityValidator().validate(
        _role_output("government_notice"), _context(article)
    )

    assert roles == []


def test_generic_official_institution_is_not_operator() -> None:
    article = Article(
        news_id=1,
        title="机构说明",
        content="该机构表示救援工作已经展开。",
        is_official=True,
        account_type="官方机构",
        source_type="机构",
    )

    _, roles = SemanticCredibilityValidator().validate(
        _role_output("operator"), _context(article)
    )

    assert roles == []


@pytest.mark.parametrize(
    ("article", "role"),
    [
        (Article(news_id=1, title="政务通报", content="救援工作已经展开。", account_type="政务账号", source_type="政府部门"), "government_notice"),
        (Article(news_id=1, title="企业说明", content="救援工作已经展开。", account_type="企业官方账号", source_type="运营方"), "operator"),
    ],
)
def test_explicit_publisher_metadata_can_admit_role(article, role) -> None:
    _, roles = SemanticCredibilityValidator().validate(_role_output(role), _context(article))

    assert len(roles) == 1
    assert roles[0].publisher_role == role
    assert roles[0].basis == "publisher_metadata"


def test_publisher_and_attributed_roles_remain_separate() -> None:
    quote = "应急管理部门表示"
    article = Article(
        news_id=1,
        title="媒体报道",
        content=f"{quote}救援工作已经展开。",
        platform="新闻网站",
        account_type="新闻媒体",
        source_type="报纸",
    )

    _, roles = SemanticCredibilityValidator().validate(
        _role_output("news_media", "emergency_management", quote), _context(article)
    )

    assert [(item.publisher_role, item.attributed_role) for item in roles] == [
        ("news_media", "emergency_management")
    ]


def test_same_core_subject_requires_substantial_factual_overlap() -> None:
    validator = SemanticCredibilityValidator()

    assert not validator._same_core_subject("设备故障", "设备已经恢复")
    assert not validator._same_core_subject("人员已撤离", "无人员伤亡")
    assert validator._same_core_subject(
        "初步原因是控制模块故障",
        "最终原因是控制模块故障",
        "控制模块故障",
    )
