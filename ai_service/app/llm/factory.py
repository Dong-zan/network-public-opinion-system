from typing import Any

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.deepseek_provider import DeepSeekProvider
from app.llm.fake_provider import FakeLLMProvider


class UnsupportedLLMProviderError(ValueError):
    """Raised when AI_LLM_PROVIDER names an unsupported provider."""


def create_llm_provider(
    provider_name: str,
    *,
    config: Settings | None = None,
    client: Any | None = None,
) -> LLMProvider:
    normalized = provider_name.strip().lower()
    if normalized == "fake":
        return FakeLLMProvider()
    if normalized == "deepseek":
        resolved_config = config or Settings(llm_provider="deepseek")
        return DeepSeekProvider(resolved_config, client=client)
    raise UnsupportedLLMProviderError(
        f"Unsupported AI_LLM_PROVIDER: {provider_name!r}. Supported: fake, deepseek"
    )
