"""OpenAI provider stub for future Phase 2B work."""

from __future__ import annotations

import os

from .base import BaseProvider, CompletionResult, ProviderError


class OpenAIProvider(BaseProvider):
    def __init__(self, model: str = ""):
        self.model = model or os.getenv("OPENAI_MODEL", "openai-configured-model")

    @property
    def name(self) -> str:
        return f"openai-{self.model}"

    def is_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY", "").strip())

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        raise ProviderError("OpenAI provider is not implemented yet")
