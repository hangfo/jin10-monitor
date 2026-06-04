"""Anthropic Messages API provider for dashboard analysis."""

from __future__ import annotations

import os
from typing import Any

from .base import BaseProvider, CompletionResult, ProviderError
from .http_json import DEFAULT_PROVIDER_TIMEOUT_SECONDS, env_float, env_int, post_json


DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(BaseProvider):
    def __init__(
        self,
        model: str = "",
        *,
        base_url: str = "",
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ):
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self.base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL") or DEFAULT_ANTHROPIC_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else env_float(
            "PROVIDER_TIMEOUT_SECONDS",
            DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        )
        self.max_tokens = max_tokens if max_tokens is not None else env_int("ANTHROPIC_MAX_TOKENS", 1800)

    @property
    def name(self) -> str:
        return f"anthropic-{self.model}"

    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": env_float("ANTHROPIC_TEMPERATURE", 0.2, minimum=0.0, maximum=1.0),
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        response = self._post_json(payload, api_key=api_key)
        parts = response.get("content") or []
        text = "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            raise ProviderError("Anthropic returned an empty response")
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        return CompletionResult(
            text=text,
            model_label=f"anthropic:{response.get('model') or self.model}",
            input_tokens=_optional_int(usage.get("input_tokens")),
            output_tokens=_optional_int(usage.get("output_tokens")),
        )

    def _post_json(self, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        return post_json(
            f"{self.base_url}/v1/messages",
            payload,
            headers={
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
                "x-api-key": api_key,
            },
            timeout_seconds=self.timeout_seconds,
        )


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
