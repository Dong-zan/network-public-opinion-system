import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.llm.base import LLMProviderConfigurationError


_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _load_environment(dotenv_path: Path = _DOTENV_PATH) -> None:
    """Load local development settings without overriding the process environment."""
    load_dotenv(dotenv_path=dotenv_path, override=False)


_load_environment()


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise LLMProviderConfigurationError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    service_name: str = field(default_factory=lambda: os.getenv("AI_SERVICE_NAME", "ai_service"))
    qa_top_k: int = field(default_factory=lambda: _positive_int("AI_QA_TOP_K", 5))
    article_max_chars: int = field(default_factory=lambda: _positive_int("AI_ARTICLE_MAX_CHARS", 1000))
    report_top_k: int = field(default_factory=lambda: _positive_int("AI_REPORT_TOP_K", 5))
    report_article_max_chars: int = field(
        default_factory=lambda: _positive_int("AI_REPORT_ARTICLE_MAX_CHARS", 1000)
    )
    verify_max_candidates: int = field(
        default_factory=lambda: _positive_int("AI_VERIFY_MAX_CANDIDATES", 50)
    )
    verify_max_sentences_per_article: int = field(
        default_factory=lambda: _positive_int("AI_VERIFY_MAX_SENTENCES_PER_ARTICLE", 100)
    )
    verify_article_max_chars: int = field(
        default_factory=lambda: _positive_int("AI_VERIFY_ARTICLE_MAX_CHARS", 5000)
    )
    verify_semantic_enabled: bool = field(
        default_factory=lambda: _boolean("AI_VERIFY_SEMANTIC_ENABLED", False)
    )
    verify_semantic_article_max_chars: int = field(
        default_factory=lambda: _positive_int("AI_VERIFY_SEMANTIC_ARTICLE_MAX_CHARS", 5000)
    )
    verify_semantic_max_flags: int = field(
        default_factory=lambda: _positive_int("AI_VERIFY_SEMANTIC_MAX_FLAGS", 12)
    )
    verify_explanation_enabled: bool = field(
        default_factory=lambda: _boolean("AI_VERIFY_EXPLANATION_ENABLED", True)
    )
    verify_explanation_article_max_chars: int = field(
        default_factory=lambda: _positive_int(
            "AI_VERIFY_EXPLANATION_ARTICLE_MAX_CHARS", 6000
        )
    )
    evidence_graph_max_articles: int = field(
        default_factory=lambda: _positive_int("AI_EVIDENCE_GRAPH_MAX_ARTICLES", 12)
    )
    evidence_graph_max_claims_per_article: int = field(
        default_factory=lambda: _positive_int(
            "AI_EVIDENCE_GRAPH_MAX_CLAIMS_PER_ARTICLE", 5
        )
    )
    evidence_graph_max_edges: int = field(
        default_factory=lambda: _positive_int("AI_EVIDENCE_GRAPH_MAX_EDGES", 60)
    )
    evidence_graph_article_max_chars: int = field(
        default_factory=lambda: _positive_int(
            "AI_EVIDENCE_GRAPH_ARTICLE_MAX_CHARS", 6000
        )
    )
    evidence_graph_llm_enabled: bool = field(
        default_factory=lambda: _boolean("AI_EVIDENCE_GRAPH_LLM_ENABLED", True)
    )
    evidence_graph_max_nodes: int = field(
        default_factory=lambda: _positive_int("AI_EVIDENCE_GRAPH_MAX_NODES", 40)
    )
    llm_provider: str = field(default_factory=lambda: os.getenv("AI_LLM_PROVIDER", "fake"))
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    )
    deepseek_thinking_enabled: bool = field(
        default_factory=lambda: _boolean("DEEPSEEK_THINKING_ENABLED", False)
    )
    deepseek_timeout_seconds: float = field(
        default_factory=lambda: _positive_float("DEEPSEEK_TIMEOUT_SECONDS", 45.0)
    )
    deepseek_max_tokens: int = field(
        default_factory=lambda: _positive_int("DEEPSEEK_MAX_TOKENS", 3000)
    )
    deepseek_temperature: float = field(
        default_factory=lambda: _float("DEEPSEEK_TEMPERATURE", 0.2)
    )

    def __post_init__(self) -> None:
        provider = self.llm_provider.strip().lower()
        if provider not in {"fake", "deepseek"}:
            raise LLMProviderConfigurationError(
                f"Unsupported AI_LLM_PROVIDER: {self.llm_provider!r}. Supported: fake, deepseek"
            )
        if provider == "deepseek" and not self.deepseek_api_key.strip():
            raise LLMProviderConfigurationError(
                "DEEPSEEK_API_KEY is required when AI_LLM_PROVIDER=deepseek"
            )
        if not self.deepseek_base_url.strip():
            raise LLMProviderConfigurationError("DEEPSEEK_BASE_URL cannot be empty")
        if not self.deepseek_model.strip():
            raise LLMProviderConfigurationError("DEEPSEEK_MODEL cannot be empty")


settings = Settings()
