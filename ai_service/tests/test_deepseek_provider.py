from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.llm.base import (
    LLMProvider,
    LLMProviderConfigurationError,
    LLMProviderError,
    LLMProviderUnavailableError,
)
from app.llm.deepseek_provider import DeepSeekProvider
from app.llm.factory import create_llm_provider
from app.llm.fake_provider import FakeLLMProvider
from app.llm.prompts import PromptBundle
from app.schemas.event import EventContext
from app.services.qa_service import QAService


def deepseek_config(**overrides) -> Settings:
    values = {
        "llm_provider": "deepseek",
        "deepseek_api_key": "unit-test-placeholder",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-flash",
        "deepseek_thinking_enabled": False,
        "deepseek_timeout_seconds": 45,
        "deepseek_max_tokens": 1000,
        "deepseek_temperature": 0.2,
    }
    values.update(overrides)
    return Settings(**values)


def response_with(content: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("supplier detail must stay private")
        self.status_code = status_code


def test_provider_factory_fake() -> None:
    assert isinstance(create_llm_provider("fake"), FakeLLMProvider)


def test_provider_factory_deepseek() -> None:
    client = MagicMock()

    provider = create_llm_provider("deepseek", config=deepseek_config(), client=client)

    assert isinstance(provider, DeepSeekProvider)
    assert provider.name == "deepseek"


def test_deepseek_missing_api_key_fails_safely() -> None:
    config = Settings(llm_provider="fake", deepseek_api_key="")

    with pytest.raises(LLMProviderConfigurationError, match="DEEPSEEK_API_KEY") as error:
        DeepSeekProvider(config, client=MagicMock())

    assert "unit-test-placeholder" not in str(error.value)


def test_deepseek_provider_sends_system_and_user_messages() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = response_with("最终回答")
    provider = DeepSeekProvider(deepseek_config(), client=client)
    prompt = PromptBundle(system_prompt="系统约束", user_prompt="用户问题与事件上下文")

    answer = provider.generate(prompt)

    assert answer == "最终回答"
    request = client.chat.completions.create.call_args.kwargs
    assert request["messages"] == [
        {"role": "system", "content": "系统约束"},
        {"role": "user", "content": "用户问题与事件上下文"},
    ]
    assert request["stream"] is False


def test_deepseek_provider_uses_configured_model() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = response_with("回答")
    provider = DeepSeekProvider(
        deepseek_config(deepseek_model="configured-model", deepseek_max_tokens=321),
        client=client,
    )

    provider.generate(PromptBundle("system", "user"))

    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == "configured-model"
    assert request["max_tokens"] == 321


def test_deepseek_provider_disables_thinking_by_default() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = response_with("回答")
    provider = DeepSeekProvider(deepseek_config(), client=client)

    provider.generate(PromptBundle("system", "user"))

    request = client.chat.completions.create.call_args.kwargs
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert request["temperature"] == 0.2


def test_thinking_mode_omits_temperature() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = response_with("回答")
    provider = DeepSeekProvider(
        deepseek_config(deepseek_thinking_enabled=True),
        client=client,
    )

    provider.generate(PromptBundle("system", "user"))

    request = client.chat.completions.create.call_args.kwargs
    assert request["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "temperature" not in request


def test_deepseek_empty_content_raises_provider_error() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = response_with("   ")
    provider = DeepSeekProvider(deepseek_config(), client=client)

    with pytest.raises(LLMProviderError):
        provider.generate(PromptBundle("system", "user"))


def test_deepseek_timeout_maps_to_unavailable_error() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = TimeoutError("private timeout detail")
    provider = DeepSeekProvider(deepseek_config(), client=client, sleep=lambda _: None)

    with pytest.raises(LLMProviderUnavailableError):
        provider.generate(PromptBundle("system", "user"))

    assert client.chat.completions.create.call_count == 1


def test_deepseek_401_is_not_retried() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = StatusError(401)
    sleeps = []
    provider = DeepSeekProvider(deepseek_config(), client=client, sleep=sleeps.append)

    with pytest.raises(LLMProviderConfigurationError):
        provider.generate(PromptBundle("system", "user"))

    assert client.chat.completions.create.call_count == 1
    assert sleeps == []


def test_deepseek_429_can_retry() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = [StatusError(429), response_with("重试后回答")]
    sleeps = []
    provider = DeepSeekProvider(deepseek_config(), client=client, sleep=sleeps.append)

    answer = provider.generate(PromptBundle("system", "user"))

    assert answer == "重试后回答"
    assert client.chat.completions.create.call_count == 2
    assert sleeps == [0.1]


def test_deepseek_retries_at_most_twice() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = StatusError(503)
    sleeps = []
    provider = DeepSeekProvider(deepseek_config(), client=client, sleep=sleeps.append)

    with pytest.raises(LLMProviderUnavailableError):
        provider.generate(PromptBundle("system", "user"))

    assert client.chat.completions.create.call_count == 3
    assert sleeps == [0.1, 0.2]


class FinalAnswerProvider(LLMProvider):
    name = "deepseek"

    def generate(self, prompt: PromptBundle) -> str:
        del prompt
        return "这是模型返回的最终文本。"


def test_open_question_returns_provider_final_content(event_payload) -> None:
    event = EventContext.model_validate(event_payload)
    service = QAService(provider=FinalAnswerProvider())

    result = service.answer(event, "这个事件发生了什么？")

    assert result.answer == "这是模型返回的最终文本。"
