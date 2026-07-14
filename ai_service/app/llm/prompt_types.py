from dataclasses import dataclass


@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    user_prompt: str
