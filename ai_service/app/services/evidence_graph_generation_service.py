import json
import logging
from functools import lru_cache

from pydantic import ValidationError

from app.core.config import settings
from app.llm.base import LLMProvider, LLMProviderError
from app.llm.evidence_graph_prompts import build_evidence_graph_prompt
from app.llm.factory import create_llm_provider
from app.schemas.evidence_graph import EvidenceGraphResponse
from app.schemas.evidence_graph_llm import EvidenceGraphLLMOutput
from app.schemas.event import EventContext
from app.services.evidence_graph_llm_validator import (
    EvidenceGraphLLMValidationError,
    EvidenceGraphLLMValidator,
)
from app.services.evidence_graph_service import EvidenceGraphService


logger = logging.getLogger(__name__)


class EvidenceGraphGenerationService:
    def __init__(
        self,
        provider: LLMProvider,
        fallback_service: EvidenceGraphService,
        *,
        llm_enabled: bool,
        max_articles: int,
        article_max_chars: int,
        max_nodes: int,
        max_edges: int,
        validator: EvidenceGraphLLMValidator | None = None,
    ) -> None:
        self.provider = provider
        self.fallback_service = fallback_service
        self.llm_enabled = llm_enabled
        self.max_articles = max(max_articles, 1)
        self.article_max_chars = max(article_max_chars, 1)
        self.validator = validator or EvidenceGraphLLMValidator(
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def build(self, event: EventContext) -> EvidenceGraphResponse:
        if (
            not self.llm_enabled
            or self.provider.name == "fake"
            or not event.articles
        ):
            return self._fallback(event, reason="llm_disabled_or_unavailable")

        selected_articles = list(event.articles[: self.max_articles])
        articles_truncated = len(event.articles) > self.max_articles
        content_truncated = any(
            len(article.content) > self.article_max_chars
            for article in selected_articles
        )
        prompt = build_evidence_graph_prompt(
            event,
            selected_articles,
            self.article_max_chars,
        )
        try:
            raw_output = self.provider.generate(prompt)
            parsed = self._parse(raw_output)
            return self.validator.finalize(
                event,
                selected_articles,
                parsed,
                articles_truncated=articles_truncated,
                content_truncated=content_truncated,
            )
        except (
            LLMProviderError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
            ValidationError,
            EvidenceGraphLLMValidationError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning(
                "evidence_graph_llm_fallback provider=%s error_type=%s",
                self.provider.name,
                type(exc).__name__,
            )
            return self._fallback(event, reason=type(exc).__name__)

    @staticmethod
    def _parse(raw_output: str) -> EvidenceGraphLLMOutput:
        text = raw_output.strip()
        if not text:
            raise ValueError("Evidence graph provider returned an empty response")
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise TypeError("Evidence graph output must be a JSON object")
        try:
            return EvidenceGraphLLMOutput.model_validate(payload)
        except ValidationError:
            raise

    def _fallback(self, event: EventContext, *, reason: str) -> EvidenceGraphResponse:
        response = self.fallback_service.build(event)
        summary = response.summary or self._fallback_summary(response)
        limitations = list(response.limitations)
        if self.llm_enabled and self.provider.name != "fake":
            limitations.append("模型图谱生成不可用，本次已使用确定性证据图谱降级结果。")
        risk_flags = list(response.risk_flags)
        if reason != "llm_disabled_or_unavailable":
            risk_flags.append("evidence_graph_llm_fallback")
        return response.model_copy(
            update={
                "summary": summary,
                "risk_flags": self._stable_unique(risk_flags),
                "limitations": self._stable_unique(limitations),
                "analysis_method": "deterministic_fallback",
                "fallback_used": True,
            }
        )

    @staticmethod
    def _fallback_summary(response: EvidenceGraphResponse) -> str:
        metrics = response.metrics
        if metrics.article_count == 0:
            return "当前事件未提供可用于构建证据图谱的文章。"
        return (
            f"当前降级图谱包含{metrics.article_count}篇文章、"
            f"{metrics.claim_cluster_count}个主张簇和"
            f"{metrics.contradiction_edge_count}条冲突关系。"
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
def get_evidence_graph_generation_service() -> EvidenceGraphGenerationService:
    fallback_service = EvidenceGraphService(
        max_articles=settings.evidence_graph_max_articles,
        max_claims_per_article=settings.evidence_graph_max_claims_per_article,
        max_edges=settings.evidence_graph_max_edges,
        article_max_chars=settings.evidence_graph_article_max_chars,
    )
    return EvidenceGraphGenerationService(
        provider=create_llm_provider(settings.llm_provider, config=settings),
        fallback_service=fallback_service,
        llm_enabled=settings.evidence_graph_llm_enabled,
        max_articles=settings.evidence_graph_max_articles,
        article_max_chars=settings.evidence_graph_article_max_chars,
        max_nodes=settings.evidence_graph_max_nodes,
        max_edges=settings.evidence_graph_max_edges,
    )
