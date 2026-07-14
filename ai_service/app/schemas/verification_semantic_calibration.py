from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.verification import (
    ClaimVerificationResult,
    LanguageRiskType,
    SourceRole,
)
from app.schemas.verification_semantic import SemanticLLMOutput


REPEATED_SEMANTIC_COLLECTION_SCHEMA_VERSION = "2.0"


class CalibrationSourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: int | str = 1
    source: str = ""
    url: str = ""
    platform: str = ""
    is_official: bool | None = None
    account_type: str | None = None
    source_type: str | None = None
    author: str | None = None


class CalibrationRoleExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: int = Field(ge=1)
    publisher_role: SourceRole = "unknown"
    attributed_role: SourceRole = "unknown"


class SemanticCalibrationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    target_title: str
    target_content: str
    source_metadata: CalibrationSourceMetadata
    claim_results: list[ClaimVerificationResult] = Field(default_factory=list)
    candidate_output: dict[str, Any]
    expected_flag_types: list[LanguageRiskType] = Field(default_factory=list)
    forbidden_flag_types: list[LanguageRiskType] = Field(default_factory=list)
    expected_role_assessments: list[CalibrationRoleExpectation] = Field(default_factory=list)
    forbidden_role_assessments: list[CalibrationRoleExpectation] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def validate_expectations(self):
        overlap = set(self.expected_flag_types) & set(self.forbidden_flag_types)
        if overlap:
            raise ValueError(f"expected和forbidden不能包含相同flag: {sorted(overlap)}")
        return self


class SemanticCalibrationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    cases: list[SemanticCalibrationCase] = Field(min_length=30)

    @model_validator(mode="after")
    def validate_unique_case_ids(self):
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id必须唯一")
        return self


class SavedSemanticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    output: dict[str, Any]


class SavedSemanticOutputBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: list[SavedSemanticOutput]

    @model_validator(mode="after")
    def validate_unique_case_ids(self):
        case_ids = [item.case_id for item in self.outputs]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("saved output的case_id必须唯一")
        return self


CollectionRunStatus = Literal["success", "failed"]
CollectionErrorType = Literal[
    "provider_timeout",
    "provider_connection_error",
    "empty_output",
    "invalid_json",
    "schema_validation_error",
    "unknown_provider_error",
]


class CalibrationRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_version: str = Field(min_length=1)
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    actual_model: str = Field(min_length=1)
    run_label: str | None = None
    article_max_chars: int = Field(gt=0)
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = None
    thinking_enabled: bool | None = None
    collection_schema_version: str = Field(min_length=1)
    created_at: datetime
    code_commit: str | None = None

    @field_validator("run_label", "code_commit", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class RepeatedSemanticRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: CollectionRunStatus
    latency_ms: float = Field(ge=0)
    raw_output: str | None = None
    parsed_output: SemanticLLMOutput | None = None
    error_type: CollectionErrorType | None = None

    @model_validator(mode="after")
    def validate_status_payload(self):
        if self.status == "success":
            if self.parsed_output is None:
                raise ValueError("成功运行必须包含parsed_output")
            if self.error_type is not None:
                raise ValueError("成功运行不能包含error_type")
        elif self.error_type is None:
            raise ValueError("失败运行必须包含安全error_type")
        return self


class RepeatedSemanticOutputBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    created_at: datetime
    metadata: CalibrationRunMetadata | None = None
    runs: list[RepeatedSemanticRun] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_runs(self):
        identities = [(item.case_id, item.run_id) for item in self.runs]
        if len(identities) != len(set(identities)):
            raise ValueError("(case_id, run_id)组合必须唯一")
        return self


class CalibrationTypeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: int = Field(ge=0)
    accepted: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)


class SemanticCalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_count: int = Field(ge=0)
    expected_flag_count: int = Field(ge=0)
    accepted_flag_count: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    per_flag_type: dict[str, CalibrationTypeMetrics]
    role_assessment_pass_rate: float = Field(ge=0, le=1)
    invalid_quote_count: int = Field(ge=0)
    invalid_evidence_reference_count: int = Field(ge=0)
    schema_failure_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    failed_case_ids: list[str] = Field(default_factory=list)


class RepeatedSemanticCalibrationReport(SemanticCalibrationReport):
    metadata: CalibrationRunMetadata | None = None
    run_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    invalid_json_count: int = Field(ge=0)
    empty_output_count: int = Field(ge=0)
    provider_failure_count: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    fallback_rate: float = Field(ge=0, le=1)
    invalid_claim_id_count: int = Field(ge=0)
    rejected_candidate_count: int = Field(ge=0)
    neutral_case_false_positive_rate: float = Field(ge=0, le=1)
    exact_flag_set_agreement_rate: float = Field(ge=0, le=1)
    average_flag_set_jaccard: float = Field(ge=0, le=1)
    per_case_flag_set_consistency: dict[str, float]
    per_flag_type_detection_consistency: dict[str, float]
    role_assessment_consistency: float = Field(ge=0, le=1)
    latency_count: int = Field(ge=0)
    latency_mean_ms: float = Field(ge=0)
    latency_p50_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)
    latency_max_ms: float = Field(ge=0)
