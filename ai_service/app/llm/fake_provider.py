from app.llm.base import LLMProvider
from app.llm.prompts import PromptBundle


class FakeLLMProvider(LLMProvider):
    """Stable offline provider used only by tests and offline integration."""

    name = "fake"

    def generate(self, prompt: PromptBundle) -> str:
        del prompt
        return "当前为离线 Fake Provider 模式，以下仅整理与问题最相关的已知报道证据。"
