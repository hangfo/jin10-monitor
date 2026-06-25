"""Google Gemini API provider for dashboard analysis."""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

from .base import BaseProvider, CompletionResult, ProviderError
from .http_json import DEFAULT_PROVIDER_TIMEOUT_SECONDS, env_float, env_int, post_json


DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_MAX_TOKENS = 8192
DEFAULT_GEMINI_THINKING_BUDGET = 0


class GeminiProvider(BaseProvider):
    def __init__(
        self,
        model: str = "",
        *,
        base_url: str = "",
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ):
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.base_url = (base_url or os.getenv("GEMINI_BASE_URL") or DEFAULT_GEMINI_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else env_float(
            "PROVIDER_TIMEOUT_SECONDS",
            DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        )
        self.max_tokens = max_tokens if max_tokens is not None else env_int("GEMINI_MAX_TOKENS", DEFAULT_GEMINI_MAX_TOKENS)
        self.thinking_budget = env_int(
            "GEMINI_THINKING_BUDGET",
            DEFAULT_GEMINI_THINKING_BUDGET,
            minimum=-1,
            maximum=24576,
        )

    @property
    def name(self) -> str:
        return f"gemini-{self.model}"

    def is_available(self) -> bool:
        return bool(_api_key())

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        api_key = _api_key()
        if not api_key:
            raise ProviderError("GEMINI_API_KEY or GOOGLE_API_KEY is not configured")
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": env_float("GEMINI_TEMPERATURE", 0.2, minimum=0.0, maximum=2.0),
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        if self.thinking_budget >= 0:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        response = self._post_json(payload, api_key=api_key)
        candidates = response.get("candidates") or []
        if not candidates or not isinstance(candidates[0], dict):
            raise ProviderError("Gemini returned no candidates")
        finish_reason = str(candidates[0].get("finishReason") or "")
        content = candidates[0].get("content") if isinstance(candidates[0].get("content"), dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        text = "\n".join(
            str(part.get("text") or "")
            for part in parts or []
            if isinstance(part, dict) and part.get("thought") is not True
        ).strip()
        if finish_reason and finish_reason != "STOP":
            detail = str(candidates[0].get("finishMessage") or "").strip()
            suffix = f": {detail}" if detail else ""
            raise ProviderError(f"Gemini stopped with finishReason={finish_reason}{suffix}")
        if not text:
            raise ProviderError("Gemini returned an empty response")
        usage = response.get("usageMetadata") if isinstance(response.get("usageMetadata"), dict) else {}
        return CompletionResult(
            text=text,
            model_label=f"gemini:{self.model}",
            input_tokens=_optional_int(usage.get("promptTokenCount")),
            output_tokens=_optional_int(usage.get("candidatesTokenCount")),
            finish_reason=finish_reason,
        )

    def _post_json(self, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        model_path = urllib.parse.quote(self.model, safe="")
        return post_json(
            f"{self.base_url}/v1beta/models/{model_path}:generateContent",
            payload,
            headers={
                "content-type": "application/json",
                "x-goog-api-key": api_key,
            },
            timeout_seconds=self.timeout_seconds,
        )


def _api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
