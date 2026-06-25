"""OpenAI-compatible chat completions provider for DeepSeek, GLM, and similar APIs."""

from __future__ import annotations

import os
from typing import Any

from .base import BaseProvider, CompletionResult, ProviderError
from .http_json import DEFAULT_PROVIDER_TIMEOUT_SECONDS, env_float, env_int, post_json


DEFAULT_COMPAT_BASE_URL = "https://api.deepseek.com"
DEFAULT_COMPAT_MODEL = "deepseek-v4-flash"
DEFAULT_COMPAT_MAX_TOKENS = 1800
DEFAULT_GLM_MAX_TOKENS = 8192


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        model: str = "",
        *,
        base_url: str = "",
        api_key_env: str = "COMPAT_LLM_API_KEY",
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ):
        self.api_key_env = api_key_env
        self.model = model or os.getenv("COMPAT_LLM_MODEL", DEFAULT_COMPAT_MODEL)
        self.base_url = (base_url or os.getenv("COMPAT_LLM_BASE_URL") or DEFAULT_COMPAT_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else env_float(
            "PROVIDER_TIMEOUT_SECONDS",
            DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        )
        default_max_tokens = (
            DEFAULT_GLM_MAX_TOKENS
            if _looks_like_glm(self.model, self.base_url, os.getenv("COMPAT_LLM_LABEL"))
            else DEFAULT_COMPAT_MAX_TOKENS
        )
        self.max_tokens = max_tokens if max_tokens is not None else env_int("COMPAT_LLM_MAX_TOKENS", default_max_tokens)

    @property
    def name(self) -> str:
        return f"compatible-{self.model}"

    def is_available(self) -> bool:
        return bool(os.getenv(self.api_key_env, "").strip())

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        api_key = os.getenv(self.api_key_env, "").strip()
        if not api_key:
            raise ProviderError(f"{self.api_key_env} is not configured")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": env_float("COMPAT_LLM_TEMPERATURE", 0.2, minimum=0.0, maximum=2.0),
            "max_tokens": self.max_tokens,
        }
        if _looks_like_glm(self.model, self.base_url, os.getenv("COMPAT_LLM_LABEL")):
            thinking_type = os.getenv("COMPAT_LLM_THINKING_TYPE", "disabled").strip().lower()
            if thinking_type in {"enabled", "disabled"}:
                payload["thinking"] = {"type": thinking_type}
        response = self._post_json(payload, api_key=api_key)
        choices = response.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise ProviderError("compatible provider returned no choices")
        message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        text = str(message.get("content") or "").strip()
        if not text:
            raise ProviderError(f"compatible provider returned an empty response; {_response_brief(response, choices[0])}")
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        return CompletionResult(
            text=text,
            model_label=f"{os.getenv('COMPAT_LLM_LABEL', 'compatible')}:{response.get('model') or self.model}",
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
        )

    def _post_json(self, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        return post_json(
            f"{self.base_url.rstrip('/')}/chat/completions",
            payload,
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            timeout_seconds=self.timeout_seconds,
        )


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _looks_like_glm(*values: object) -> bool:
    text = " ".join(str(value or "").lower() for value in values)
    return "glm" in text or "bigmodel.cn" in text or "zhipu" in text


def _response_brief(response: dict[str, Any], choice: dict[str, Any]) -> str:
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    parts = [
        f"model={response.get('model') or ''}",
        f"finish_reason={choice.get('finish_reason') or choice.get('finishReason') or ''}",
        f"message_keys={','.join(str(key) for key in message.keys())}",
    ]
    if usage:
        parts.append(
            "usage="
            + ",".join(f"{key}={value}" for key, value in usage.items() if key in {"prompt_tokens", "completion_tokens", "total_tokens"})
        )
    return "; ".join(part for part in parts if part and not part.endswith("="))
