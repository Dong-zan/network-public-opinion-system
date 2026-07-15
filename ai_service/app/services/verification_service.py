from functools import lru_cache
from app.core.config import settings
from app.schemas.event import Article, EventContext
from app.schemas.verification import (
    ClaimVerificationResult,
    VerificationContextEvidence,
    VerificationEvidence,
    VerificationResponse,
    VerificationVerdict,
)
from app.services.claim_extractor import AtomicClaim, ClaimExtractor
from app.services.credibility_assessment_service import (
    CredibilityAssessmentService,
    InputIntegrityMetadata,
)
from app.services.evidence_retriever import EvidenceRetriever
from app.services.evidence_validator import EvidenceValidator
from app.services.evidence_source_assessment import EvidenceSourceAssessmentService
from app.services.verification_scorer import VerificationScorer
from app.services.source_clusterer import SourceClusterer, SourceDescriptor
from app.services.verification_display import VerificationDisplayBuilder
from app.services.verification_explanation import VerificationExplanationService


class TargetArticleNotFoundError(ValueError):
    """Raised when the requested article is absent from the supplied event."""


class VerificationService:
    def __init__(
        self,
        extractor: ClaimExtractor | None = None,
        retriever: EvidenceRetriever | None = None,
        validator: EvidenceValidator | None = None,
        scorer: VerificationScorer | None = None,
        credibility_assessment_service: CredibilityAssessmentService | None = None,
        explanation_service: VerificationExplanationService | None = None,
        evidence_source_assessment_service: EvidenceSourceAssessmentService | None = None,
        display_builder: VerificationDisplayBuilder | None = None,
        *,
        max_candidates: int = 50,
        max_sentences_per_article: int = 100,
        article_max_chars: int = 5000,
    ) -> None:
        self.extractor = extractor or ClaimExtractor()
        self.max_candidates = max(max_candidates, 1)
        self.max_sentences_per_article = max(max_sentences_per_article, 1)
        self.article_max_chars = max(article_max_chars, 1)
        self.retriever = retriever or EvidenceRetriever(
            max_candidates=self.max_candidates,
            max_sentences_per_article=self.max_sentences_per_article,
            article_max_chars=self.article_max_chars,
        )
        self.validator = validator or EvidenceValidator()
        self.scorer = scorer or VerificationScorer()
        self.credibility_assessment_service = (
            credibility_assessment_service or CredibilityAssessmentService()
        )
        self.explanation_service = explanation_service
        self.evidence_source_assessment_service = (
            evidence_source_assessment_service
            or EvidenceSourceAssessmentService(
                self.credibility_assessment_service.source_evaluator
            )
        )
        self.display_builder = display_builder or VerificationDisplayBuilder()

    def verify(
        self,
        event: EventContext,
        target_news_id: int | str,
        max_claims: int = 5,
    ) -> VerificationResponse:
        target = self._find_target(event.articles, target_news_id)
        target_truncated = len(target.content) > self.article_max_chars
        bounded_target = target.model_copy(
            update={"content": target.content[: self.article_max_chars]}
        )
        claims = self.extractor.extract(bounded_target, max_claims)
        selection = self.retriever.select_candidates(event.articles, target)

        claim_results = []
        sentence_limit_applied = False
        evidence_article_truncated = False
        evolving_information = False
        for index, claim in enumerate(claims, start=1):
            result, sentence_limited, article_truncated, evolved = self._verify_claim(
                claim_id=index,
                claim=claim,
                candidates=selection.articles,
                event=event,
                target=target,
            )
            claim_results.append(result)
            sentence_limit_applied = sentence_limit_applied or sentence_limited
            evidence_article_truncated = evidence_article_truncated or article_truncated
            evolving_information = evolving_information or evolved

        overall_verdict = self._overall_verdict(claim_results)
        verifiable_count = sum(
            result.verdict != "not_verifiable" for result in claim_results
        )
        determinate_count = sum(
            result.verdict in {"supported", "contradicted", "conflicting"}
            for result in claim_results
        )
        coverage = (
            round(determinate_count / verifiable_count * 100, 1)
            if verifiable_count
            else 0.0
        )
        evidence_score = self.scorer.score(claim_results, overall_verdict)
        risk_flags = self._risk_flags(
            target=target,
            results=claim_results,
            duplicate_count=selection.duplicate_count,
            near_duplicate_fact_difference_count=(
                selection.near_duplicate_fact_difference_count
            ),
            evolving_information=evolving_information,
            input_truncated=(
                target_truncated
                or selection.candidate_limit_applied
                or bool(selection.article_truncated_count)
                or sentence_limit_applied
                or evidence_article_truncated
            ),
        )
        limitations = self._limitations(
            results=claim_results,
            candidate_count=len(selection.articles),
            duplicate_count=selection.duplicate_count,
            near_duplicate_fact_difference_count=(
                selection.near_duplicate_fact_difference_count
            ),
            evolving_information=evolving_information,
            target_truncated=target_truncated,
            candidate_limit_applied=selection.candidate_limit_applied,
            article_truncated=(
                bool(selection.article_truncated_count) or evidence_article_truncated
            ),
            sentence_limit_applied=sentence_limit_applied,
        )
        response = VerificationResponse(
            target_news_id=target.news_id if target.news_id is not None else target_news_id,
            overall_verdict=overall_verdict,
            evidence_score=evidence_score,
            claim_results=claim_results,
            risk_flags=risk_flags,
            limitations=limitations,
            verifiable_claim_count=verifiable_count,
            determinate_claim_count=determinate_count,
            verification_coverage=coverage,
            score_explanation=self._score_explanation(overall_verdict, evidence_score),
        )
        input_truncated = (
            target_truncated
            or selection.candidate_limit_applied
            or bool(selection.article_truncated_count)
            or sentence_limit_applied
            or evidence_article_truncated
        )
        assessment = self.credibility_assessment_service.assess(
            target,
            response,
            InputIntegrityMetadata(
                input_truncated=input_truncated,
                article_count=len(event.articles),
            ),
            event.articles,
        )
        evidence_source_assessments = self.evidence_source_assessment_service.assess(
            event,
            response,
        )
        completed_response = response.model_copy(
            update={
                "credibility_assessment": assessment,
                "evidence_source_assessments": evidence_source_assessments,
            }
        )
        if self.explanation_service is None:
            return completed_response
        explanation = self.explanation_service.explain(
            event,
            target,
            completed_response,
        )
        explained_response = completed_response.model_copy(
            update={"ai_explanation": explanation}
        )
        display_result = self.display_builder.build(event, explained_response)
        return explained_response.model_copy(update={"display_result": display_result})

    def _verify_claim(
        self,
        *,
        claim_id: int,
        claim: AtomicClaim,
        candidates: tuple[Article, ...],
        event: EventContext,
        target: Article,
    ) -> tuple[ClaimVerificationResult, bool, bool, bool]:
        if not claim.verifiable:
            result = ClaimVerificationResult(
                claim_id=claim_id,
                claim=claim.text,
                verdict="not_verifiable",
                independent_source_count=0,
                limitations=["该表述包含预测、建议或主观判断，当前无法作为事实主张核验。"],
                evidence_score=None,
                explanation="该表述不属于当前阶段可确定性比较的事实主张。",
            )
            return result, False, False, False

        retrieval = self.retriever.retrieve(
            claim,
            candidates,
            target_publish_time=target.publish_time,
        )
        raw_evidence = [
            VerificationEvidence(
                news_id=item.article.news_id,
                source=item.article.source,
                url=item.article.url,
                quote=item.quote,
                stance=item.stance,
                reason_code=item.reason_code,
                relevance_score=item.relevance_score,
            )
            for item in retrieval.evidence
            if item.stance in {"supports", "contradicts"}
            and item.article.news_id is not None
        ]
        evidence = self.validator.validate(
            raw_evidence,
            event.articles,
            target.news_id if target.news_id is not None else "",
        )
        raw_context_evidence = [
            VerificationContextEvidence(
                news_id=item.article.news_id,
                source=item.article.source,
                url=item.article.url,
                quote=item.quote,
                relation=item.stance,
                reason_code=item.reason_code,
                relevance_score=item.relevance_score,
            )
            for item in retrieval.evidence
            if item.stance in {"related", "updates"}
            and item.article.news_id is not None
        ]
        context_evidence = self.validator.validate_context(
            raw_context_evidence,
            event.articles,
            target.news_id if target.news_id is not None else "",
        )
        support_sources, contradict_sources = self._stance_clusters(evidence)
        verdict = self._claim_verdict(support_sources, contradict_sources, evidence)
        limitations = []
        if any(item.stance == "related" for item in retrieval.evidence):
            limitations.append(
                "部分材料仅表示仍在调查、尚未确认或缺少可比较槽位，不能支持具体事实结论。"
            )
        if any(item.stance == "updates" for item in retrieval.evidence):
            limitations.append(
                "较晚报道可能反映信息或状态演化，不作为对较早主张的直接支持或反驳。"
            )
        if verdict == "insufficient_evidence":
            limitations.append("独立来源证据不足，当前不能形成稳定核验结论。")

        provisional = ClaimVerificationResult(
            claim_id=claim_id,
            claim=claim.text,
            verdict=verdict,
            independent_source_count=len(support_sources | contradict_sources),
            evidence=evidence,
            context_evidence=context_evidence,
            limitations=self._stable_unique(limitations),
            explanation=self._claim_explanation(claim, verdict, support_sources, contradict_sources),
        )
        result = provisional.model_copy(
            update={"evidence_score": self.scorer.score_claim(provisional)}
        )
        return (
            result,
            retrieval.sentence_limit_applied,
            retrieval.article_truncated,
            any(item.stance == "updates" for item in retrieval.evidence),
        )

    @staticmethod
    def _claim_verdict(
        support_sources: set[str],
        contradict_sources: set[str],
        evidence: list[VerificationEvidence],
    ) -> VerificationVerdict:
        if support_sources and contradict_sources:
            return "conflicting"
        if len(support_sources) >= 2:
            return "supported"
        if len(contradict_sources) >= 2:
            return "contradicted"
        if evidence:
            return "insufficient_evidence"
        return "insufficient_evidence"

    @staticmethod
    def _overall_verdict(
        results: list[ClaimVerificationResult],
    ) -> VerificationVerdict:
        verifiable = [item for item in results if item.verdict != "not_verifiable"]
        if not verifiable:
            return "not_verifiable"
        verdicts = {item.verdict for item in verifiable}
        if "conflicting" in verdicts or {"supported", "contradicted"} <= verdicts:
            return "conflicting"
        if "contradicted" in verdicts:
            return "contradicted"
        if all(item.verdict == "supported" for item in verifiable):
            return "supported"
        return "insufficient_evidence"

    @staticmethod
    def _claim_explanation(
        claim: AtomicClaim,
        verdict: VerificationVerdict,
        support_sources: set[str],
        contradict_sources: set[str],
    ) -> str:
        type_name = VerificationService._claim_type_name(claim.claim_type)
        if verdict == "supported":
            return f"{len(support_sources)}个独立来源对该{type_name}主张给出了相同表述。"
        if verdict == "contradicted":
            return f"{len(contradict_sources)}个独立来源给出了与目标{type_name}主张直接冲突的表述。"
        if verdict == "conflicting":
            return "当前独立来源同时包含支持与反驳该主张的结构化证据。"
        if verdict == "not_verifiable":
            return "该表述不属于当前阶段可确定性核验的事实主张。"
        return "当前独立来源数量或可比较事实槽位不足，无法形成稳定结论。"

    @staticmethod
    def _score_explanation(
        verdict: VerificationVerdict,
        score: float,
    ) -> str:
        verdict_name = {
            "supported": "得到支持",
            "contradicted": "受到反驳",
            "conflicting": "存在冲突",
            "insufficient_evidence": "证据不足",
            "not_verifiable": "不可核验",
        }[verdict]
        if verdict == "contradicted":
            return (
                f"证据强度评分为{score:g}，表示当前反驳结论的启发式证据强度；"
                "较高分值表示反驳证据较强，不是对文章真假的概率估计。"
            )
        return (
            f"证据强度评分为{score:g}，表示当前“{verdict_name}”结论的启发式证据强度，"
            "不是对文章真假的概率估计。"
        )

    @staticmethod
    def _stance_clusters(
        evidence: list[VerificationEvidence],
    ) -> tuple[set[int], set[int]]:
        descriptors = [
            SourceDescriptor(source=item.source, url=item.url) for item in evidence
        ]
        clusterer = SourceClusterer()
        clusters = clusterer.cluster_indices(descriptors)

        support_clusters = set()
        contradict_clusters = set()
        for index, item in enumerate(evidence):
            if not any(clusterer.identity(descriptors[index])):
                continue
            target = support_clusters if item.stance == "supports" else contradict_clusters
            target.add(clusters[index])
        return support_clusters, contradict_clusters

    @staticmethod
    def _risk_flags(
        *,
        target: Article,
        results: list[ClaimVerificationResult],
        duplicate_count: int,
        near_duplicate_fact_difference_count: int,
        evolving_information: bool,
        input_truncated: bool,
    ) -> list[str]:
        flags = []
        if duplicate_count:
            flags.append("duplicate_or_reprint_evidence_removed")
        if near_duplicate_fact_difference_count:
            flags.append("near_duplicate_with_fact_difference")
        if evolving_information:
            flags.append("evolving_information")
        if any(item.verdict == "conflicting" for item in results):
            flags.append("conflicting_evidence")
        if any(
            item.verdict != "not_verifiable" and item.independent_source_count < 2
            for item in results
        ):
            flags.append("limited_independent_sources")
        if ClaimExtractor.contains_instruction(target.content):
            flags.append("untrusted_instruction_ignored")
        if not results or all(item.verdict == "not_verifiable" for item in results):
            flags.append("no_verifiable_claims")
        if input_truncated:
            flags.append("verification_input_truncated")
        return VerificationService._stable_unique(flags)

    @staticmethod
    def _limitations(
        *,
        results: list[ClaimVerificationResult],
        candidate_count: int,
        duplicate_count: int,
        near_duplicate_fact_difference_count: int,
        evolving_information: bool,
        target_truncated: bool,
        candidate_limit_applied: bool,
        article_truncated: bool,
        sentence_limit_applied: bool,
    ) -> list[str]:
        limitations = [
            "第一阶段仅核验当前事件输入中的文章，不联网搜索外部信息。",
            "证据强度评分表示当前核验结论的启发式证据强度，不代表事实为真的概率。",
        ]
        if candidate_count == 0:
            limitations.append("当前没有可作为独立证据的候选文章。")
        if duplicate_count:
            limitations.append("同编号、同URL、相同正文或正文高度重复的转载已去重。")
        if near_duplicate_fact_difference_count:
            limitations.append("部分高相似报道包含不同关键事实，已保留用于识别潜在冲突。")
        if evolving_information:
            limitations.append("部分较晚报道可能反映信息演化，未作为对较早报道的直接反驳。")
        if any(item.verdict == "insufficient_evidence" for item in results):
            limitations.append("部分主张缺少至少两个独立来源的一致证据。")
        if not results or all(item.verdict == "not_verifiable" for item in results):
            limitations.append("目标文章中未提取到当前阶段可确定性核验的事实主张。")
        if candidate_limit_applied:
            limitations.append("候选文章数量超过核验上限，已按输入顺序确定性截断。")
        if target_truncated or article_truncated:
            limitations.append("部分文章正文超过核验字符上限，已确定性截断。")
        if sentence_limit_applied:
            limitations.append("部分文章句子数量超过核验上限，已确定性截断。")
        return VerificationService._stable_unique(limitations)

    @staticmethod
    def _claim_type_name(claim_type: str) -> str:
        return {
            "casualty": "伤亡情况",
            "location": "事件地点",
            "event_time": "事件时间",
            "cause": "事件原因",
            "response_status": "处置进展",
            "conclusion_status": "调查结论",
            "quantity": "数量信息",
            "other": "其他事实",
        }.get(claim_type, "事实")

    @staticmethod
    def _find_target(
        articles: list[Article],
        target_news_id: int | str,
    ) -> Article:
        target_key = str(target_news_id).strip()
        for article in articles:
            if article.news_id is not None and str(article.news_id).strip() == target_key:
                return article
        raise TargetArticleNotFoundError(
            f"Target article {target_news_id!r} is absent from the supplied event"
        )

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result


@lru_cache
def get_verification_service() -> VerificationService:
    assessment_service = CredibilityAssessmentService()
    explanation_service = None
    provider = None
    if settings.verify_semantic_enabled or settings.verify_explanation_enabled:
        from app.llm.factory import create_llm_provider

        provider = create_llm_provider(settings.llm_provider, config=settings)
    if settings.verify_semantic_enabled:
        from app.services.semantic_credibility import LlmSemanticCredibilityAnalyzer

        assessment_service = CredibilityAssessmentService(
            semantic_analyzer=LlmSemanticCredibilityAnalyzer(
                provider,
                article_max_chars=settings.verify_semantic_article_max_chars,
                max_flags=settings.verify_semantic_max_flags,
            )
        )
    if settings.verify_explanation_enabled:
        explanation_service = VerificationExplanationService(
            provider,
            article_max_chars=settings.verify_explanation_article_max_chars,
            score_config=assessment_service.scorer.config,
        )
    return VerificationService(
        credibility_assessment_service=assessment_service,
        explanation_service=explanation_service,
        max_candidates=settings.verify_max_candidates,
        max_sentences_per_article=settings.verify_max_sentences_per_article,
        article_max_chars=settings.verify_article_max_chars,
    )
