import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from openai import APIConnectionError, APITimeoutError, OpenAI

from app.llm.base import (
    LLMProvider,
    LLMProviderConfigurationError,
    LLMProviderError,
    LLMProviderUnavailableError,
)
from app.llm.prompts import PromptBundle

if TYPE_CHECKING:
    from app.core.config import Settings


class DeepSeekProvider(LLMProvider):
    """OpenAI-compatible, non-streaming DeepSeek chat provider."""

    name = "deepseek"
    _retryable_statuses = {429, 500, 503}
    _non_retryable_configuration_statuses = {400, 401, 422}

    def __init__(
        self,
        config: "Settings",
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 2,
    ) -> None:
        if not config.deepseek_api_key.strip():
            raise LLMProviderConfigurationError(
                "DEEPSEEK_API_KEY is required when AI_LLM_PROVIDER=deepseek"
            )
        self.config = config
        self._sleep = sleep
        self._max_retries = max(0, min(max_retries, 2))
        self._client = client or OpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
            timeout=config.deepseek_timeout_seconds,
            max_retries=0,
        )

    def generate(self, prompt: PromptBundle) -> str:
        request = self._request_parameters(prompt)
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(**request)
            except Exception as exc:
                status_code = self._status_code(exc)
                if status_code in self._retryable_statuses and attempt < self._max_retries:
                    self._sleep(0.1 * (2**attempt))
                    continue
                raise self._map_exception(exc, status_code) from exc

            content = self._extract_content(response)
            if not content:
                raise LLMProviderError("DeepSeek returned an empty answer")
            return content

        raise LLMProviderUnavailableError("DeepSeek is unavailable")

    def _request_parameters(self, prompt: PromptBundle) -> dict[str, Any]:
        thinking_type = "enabled" if self.config.deepseek_thinking_enabled else "disabled"
        request: dict[str, Any] = {
            "model": self.config.deepseek_model,
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
            "stream": False,
            "max_tokens": self.config.deepseek_max_tokens,
            "extra_body": {"thinking": {"type": thinking_type}},
        }
        if not self.config.deepseek_thinking_enabled:
            request["temperature"] = self.config.deepseek_temperature
        return request

    @staticmethod
    def _extract_content(response: Any) -> str:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            return ""
        return content.strip() if isinstance(content, str) else ""

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None)
        return response_status if isinstance(response_status, int) else None

    def _map_exception(self, exc: Exception, status_code: int | None) -> LLMProviderError:
        if isinstance(exc, (APITimeoutError, TimeoutError)):
            return LLMProviderUnavailableError("DeepSeek request timed out")
        if isinstance(exc, (APIConnectionError, ConnectionError)):
            return LLMProviderUnavailableError("DeepSeek connection failed")
        if status_code in self._non_retryable_configuration_statuses:
            return LLMProviderConfigurationError("DeepSeek rejected the request configuration")
        if status_code == 402:
            return LLMProviderUnavailableError("DeepSeek account is unavailable")
        if status_code in self._retryable_statuses or (status_code is not None and status_code >= 500):
            return LLMProviderUnavailableError("DeepSeek service is unavailable")
        return LLMProviderError("DeepSeek request failed")
