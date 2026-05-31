"""Anthropic provider stub for future Phase 2B work."""

from __future__ import annotations

import os

from .base import BaseProvider, CompletionResult, ProviderError


class AnthropicProvider(BaseProvider):
    def __init__(self, model: str = ""):
        self.model = model or os.getenv("ANTHROPIC_MODEL", "anthropic-configured-model")

    @property
    def name(self) -> str:
        return f"anthropic-{self.model}"

    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        raise ProviderError("Anthropic provider is not implemented yet")
