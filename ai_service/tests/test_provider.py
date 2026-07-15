import pytest

from app.core.config import Settings
from app.llm.base import LLMProvider, LLMProviderError
from app.llm.factory import UnsupportedLLMProviderError, create_llm_provider
from app.llm.prompt_types import PromptBundle
from app.main import app
from app.services.qa_service import QAService, get_qa_service


class FailingProvider(LLMProvider):
    def generate(self, prompt: PromptBundle) -> str:
        del prompt
        raise RuntimeError("secret-provider-detail api_key=do-not-expose")


class EmptyProvider(LLMProvider):
    def generate(self, prompt: PromptBundle) -> str:
        del prompt
        return ""


@pytest.fixture
def failing_provider_override():
    app.dependency_overrides[get_qa_service] = lambda: QAService(provider=FailingProvider())
    yield
    app.dependency_overrides.pop(get_qa_service, None)


def test_provider_exception_returns_safe_503(client, event_payload, failing_provider_override) -> None:
    response = client.post(
        "/ai/ask",
        json={"event": event_payload, "question": "救援进展如何？"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "AI 问答服务暂时不可用"}
    assert "secret-provider-detail" not in response.text
    assert "api_key" not in response.text


@pytest.mark.parametrize(
    "question, expected",
    [
        ("为什么风险高？", "上游分析"),
        ("当前舆论情绪如何？", "负面50.0%"),
        ("有哪些媒体报道？", "人民网"),
    ],
)
def test_deterministic_questions_work_when_provider_fails(
    client,
    event_payload,
    failing_provider_override,
    question,
    expected,
) -> None:
    response = client.post("/ai/ask", json={"event": event_payload, "question": question})

    assert response.status_code == 200
    assert expected in response.json()["answer"]


def test_missing_trend_data_surfaces_provider_unavailability(
    client,
    event_payload,
    failing_provider_override,
) -> None:
    response = client.post(
        "/ai/ask",
        json={"event": event_payload, "question": "是在升温还是降温？"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "AI 问答服务暂时不可用"}


def test_empty_provider_response_is_rejected(event_payload) -> None:
    from app.schemas.event import EventContext

    service = QAService(provider=EmptyProvider())
    event = EventContext.model_validate(event_payload)

    with pytest.raises(LLMProviderError):
        service.answer(event, "救援进展如何？")


def test_unsupported_provider_does_not_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "unknown-provider")

    with pytest.raises(ValueError, match="Unsupported AI_LLM_PROVIDER"):
        Settings()
    with pytest.raises(UnsupportedLLMProviderError):
        create_llm_provider("unknown-provider")


def test_api_key_is_not_in_log_or_api_response(
    client,
    event_payload,
    failing_provider_override,
    caplog,
) -> None:
    response = client.post(
        "/ai/ask",
        json={"event": event_payload, "question": "救援进展如何？"},
    )

    assert response.status_code == 503
    assert "do-not-expose" not in response.text
    assert "do-not-expose" not in caplog.text
