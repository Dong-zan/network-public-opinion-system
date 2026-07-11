from abc import ABC, abstractmethod

from app.llm.prompts import PromptBundle


class LLMProviderError(RuntimeError):
    """Base exception for safe handling of provider failures."""


class LLMProviderConfigurationError(LLMProviderError, ValueError):
    """Raised when provider configuration is missing or invalid."""


class LLMProviderUnavailableError(LLMProviderError):
    """Raised when the configured provider cannot serve a request."""


class LLMProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, prompt: PromptBundle) -> str:
        """Generate text for a task without changing the supplied facts."""
