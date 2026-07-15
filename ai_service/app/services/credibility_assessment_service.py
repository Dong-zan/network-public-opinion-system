from dataclasses import dataclass

from app.schemas.event import Article
from app.schemas.verification import CredibilityAssessment, VerificationResponse
from app.services.credibility_narrative import CredibilityNarrativeBuilder
from app.services.credibility_scorer import CredibilityRiskScorer
from app.services.language_risk import DeterministicLanguageRiskAnalyzer, LanguageRiskAnalyzer
from app.services.source_traceability import SourceTraceabilityEvaluator


@dataclass(frozen=True)
class InputIntegrityMetadata:
    input_truncated: bool = False
    article_count: int = 0


@dataclass(frozen=True)
class AssessmentConfidenceConfig:
    version: str = "credibility-confidence-v1"
    coverage_weight: float = 0.40
    verifiable_weight: float = 20.0
    independent_source_weight: float = 20.0
    metadata_weight: float = 0.15
    verified_registry_bonus: float = 5.0
    partial_registry_bonus: float = 2.0
    single_article_penalty: float = 15.0
    truncated_penalty: float = 10.0
    not_verifiable_penalty: float = 10.0


class CredibilityAssessmentService:
    """Independent deterministic assessment layered on top of fact verification."""

    def __init__(
        self,
        source_evaluator: SourceTraceabilityEvaluator | None = None,
        language_analyzer: LanguageRiskAnalyzer | None = None,
        scorer: CredibilityRiskScorer | None = None,
        narrative_builder: CredibilityNarrativeBuilder | None = None,
        confidence_config: AssessmentConfidenceConfig | None = None,
        semantic_analyzer=None,
    ) -> None:
        self.source_evaluator = source_evaluator or SourceTraceabilityEvaluator()
        self.language_analyzer = language_analyzer or DeterministicLanguageRiskAnalyzer()
        self.scorer = scorer or CredibilityRiskScorer()
        self.narrative_builder = narrative_builder or CredibilityNarrativeBuilder()
        self.confidence_config = confidence_config or AssessmentConfidenceConfig()
        self.semantic_analyzer = semantic_analyzer

    def assess(
        self,
        target_article: Article,
        verification: VerificationResponse,
        integrity: InputIntegrityMetadata,
        articles: list[Article] | None = None,
    ) -> CredibilityAssessment:
        source = self.source_evaluator.evaluate(target_article)
        language = self.language_analyzer.analyze(target_article)
        score = self.scorer.score(verification, source, language)
        summary, factors = self.narrative_builder.build(verification, source, language)
        confidence = self._confidence(verification, source, integrity)
        warnings = ["综合风险分数不是文章真实性概率。"]
        if integrity.input_truncated:
            warnings.append("部分输入已确定性截断，评估覆盖可能受限。")
        if verification.overall_verdict in {"insufficient_evidence", "not_verifiable"}:
            warnings.append("当前结论受限于输入材料的独立来源数量和可核验范围。")
        assessment = CredibilityAssessment(
            version=self.scorer.config.version,
            analysis_method="deterministic",
            risk_label=score.risk_label,
            risk_score=score.risk_score,
            assessment_confidence=confidence,
            evidence_assessment=score.evidence,
            source_assessment=source,
            language_assessment=language,
            decisive_factors=factors,
            summary=summary,
            warnings=warnings,
        )
        if self.semantic_analyzer is None:
            return assessment
        semantic = self.semantic_analyzer.analyze(
            target_article,
            verification,
            assessment,
            articles or [target_article],
        )
        return assessment.model_copy(update={"semantic_assessment": semantic})

    def _confidence(self, verification: VerificationResponse, source, integrity: InputIntegrityMetadata) -> float:
        config = self.confidence_config
        average_sources = (
            sum(result.independent_source_count for result in verification.claim_results)
            / len(verification.claim_results)
            if verification.claim_results
            else 0.0
        )
        value = verification.verification_coverage * config.coverage_weight
        value += min(verification.verifiable_claim_count, 3) / 3 * config.verifiable_weight
        value += min(average_sources, 2) / 2 * config.independent_source_weight
        value += source.metadata_coverage * config.metadata_weight
        if source.status == "verified":
            value += config.verified_registry_bonus
        elif source.status == "partially_verified":
            value += config.partial_registry_bonus
        if integrity.article_count <= 1:
            value -= config.single_article_penalty
        if integrity.input_truncated:
            value -= config.truncated_penalty
        if verification.overall_verdict == "not_verifiable":
            value -= config.not_verifiable_penalty
        return round(max(0.0, min(100.0, value)), 1)
