"""Optional LLM provider interfaces for future Phase 2B work."""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from typing import Optional


class ProviderError(Exception):
    """Raised when an optional provider call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model_label: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass(frozen=True)
class ProviderStatus:
    key: str
    label: str
    configured: bool
    available: bool
    note: str


class BaseProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @abc.abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        """Return model output or raise ProviderError."""

    def is_available(self) -> bool:
        return True


def _openai_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _anthropic_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def provider_statuses() -> list[ProviderStatus]:
    return [
        ProviderStatus(
            key="manual",
            label="手工流（ChatGPT/Claude.ai）",
            configured=True,
            available=True,
            note="复制粘贴 Prompt，不需要 API key。",
        ),
        ProviderStatus(
            key="openai",
            label="OpenAI",
            configured=_openai_configured(),
            available=_openai_configured(),
            note="Phase 2B 接入前仅检查 OPENAI_API_KEY 是否存在，不发起网络请求。",
        ),
        ProviderStatus(
            key="anthropic",
            label="Anthropic",
            configured=_anthropic_configured(),
            available=_anthropic_configured(),
            note="Phase 2B 接入前仅检查 ANTHROPIC_API_KEY 是否存在，不发起网络请求。",
        ),
    ]


def get_provider(name: Optional[str]) -> Optional[BaseProvider]:
    provider_name = str(name or "").strip().lower()
    if not provider_name or provider_name == "manual":
        return None
    if provider_name == "openai":
        from .openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        return provider if provider.is_available() else None
    if provider_name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
        return provider if provider.is_available() else None
    return None
