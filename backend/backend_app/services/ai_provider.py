from abc import ABC, abstractmethod

import requests

from backend_app.config import settings


class AIProviderError(RuntimeError):
    """Safe error raised when the backend cannot obtain a usable AI response."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class AIProvider(ABC):
    provider_name = "unknown"

    @abstractmethod
    def ask(self, context: dict):
        pass

    @abstractmethod
    def report(self, context: dict):
        pass

    @abstractmethod
    def verify(self, context: dict):
        pass


class RealAIProvider(AIProvider):
    """HTTP adapter for the standalone AI service.

    The actual LLM mode (for example ``fake`` or ``deepseek``) is supplied by
    the AI service in ``X-AI-Provider`` and retained for result persistence.
    """

    BASE_URL = settings.AI_SERVER_URL

    def __init__(self):
        self.provider_name = "unknown"

    def ask(self, context: dict):
        return self._post("/ai/ask", context, timeout=60)

    def report(self, context: dict):
        return self._post("/ai/report", context, timeout=120)

    def verify(self, context: dict):
        return self._post("/ai/verify", context, timeout=60)

    def _post(self, path: str, context: dict, timeout: int):
        try:
            response = requests.post(
                f"{self.BASE_URL}{path}",
                json=context,
                timeout=timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise AIProviderError("AI service request timed out", 504) from exc
        except requests.exceptions.ConnectionError as exc:
            raise AIProviderError("AI service is unavailable", 503) from exc
        except requests.exceptions.RequestException as exc:
            raise AIProviderError("AI service request failed", 502) from exc

        self.provider_name = self._provider_name(response)

        if not response.ok:
            raise AIProviderError(
                self._error_message(response),
                self._upstream_status(response.status_code),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AIProviderError("AI service returned invalid JSON", 502) from exc

        if not isinstance(payload, dict):
            raise AIProviderError("AI service returned an invalid response", 502)
        return payload

    @staticmethod
    def _provider_name(response) -> str:
        headers = getattr(response, "headers", None)
        if not hasattr(headers, "get"):
            return "unknown"
        value = headers.get("X-AI-Provider", "unknown")
        return str(value or "unknown").strip().lower() or "unknown"

    @staticmethod
    def _upstream_status(status_code: int) -> int:
        if status_code in {400, 404, 422, 429, 503, 504}:
            return status_code
        return 502

    @staticmethod
    def _error_message(response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return "AI service request failed"
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
        return "AI service request failed"


class FakeAIProvider(AIProvider):
    provider_name = "fake"

    def ask(self, context: dict):
        question = context.get("question", "")
        return {
            "answer": f"这是测试AI回答：{question}",
            "summary": "基于当前事件数据生成的测试摘要",
            "trend": "事件热度正在变化",
            "risk": "需要持续关注",
            "suggestion": "建议结合更多数据判断",
        }

    def report(self, context: dict):
        return {
            "overview": {"title": context["event"]["title"]},
            "summary": "测试报告摘要",
            "trend_analysis": "测试趋势分析",
            "risk_analysis": "测试风险分析",
            "suggestions": ["持续关注事件发展"],
            "limitations": [],
        }

    def verify(self, context: dict):
        return {"verified": True}
