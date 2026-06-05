"""Optional LLM provider interfaces for dashboard analysis."""

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
    finish_reason: str = ""


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


def _gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip())


def _compatible_configured() -> bool:
    return bool(os.getenv("COMPAT_LLM_API_KEY", "").strip())


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
            note="配置 OPENAI_API_KEY 后可作为备用直连 provider。",
        ),
        ProviderStatus(
            key="anthropic",
            label="Anthropic",
            configured=_anthropic_configured(),
            available=_anthropic_configured(),
            note="配置 ANTHROPIC_API_KEY 后调用 Anthropic Messages API；默认不启用。",
        ),
        ProviderStatus(
            key="gemini",
            label="Gemini",
            configured=_gemini_configured(),
            available=_gemini_configured(),
            note="推荐免费优先试用项；配置 GEMINI_API_KEY 或 GOOGLE_API_KEY 后调用 Gemini API。",
        ),
        ProviderStatus(
            key="compatible",
            label=os.getenv("COMPAT_LLM_LABEL", "OpenAI Compatible"),
            configured=_compatible_configured(),
            available=_compatible_configured(),
            note="用于 DeepSeek / GLM 等 OpenAI-compatible API；配置 base URL、model 和 key 后启用。",
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
    if provider_name == "gemini":
        from .gemini_provider import GeminiProvider

        provider = GeminiProvider()
        return provider if provider.is_available() else None
    if provider_name in {"compatible", "openai_compatible", "deepseek", "glm"}:
        from .compatible_provider import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider()
        return provider if provider.is_available() else None
    return None
