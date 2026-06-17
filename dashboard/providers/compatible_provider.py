"""OpenAI-compatible chat completions provider for DeepSeek, GLM, and similar APIs."""

from __future__ import annotations

import os
from typing import Any

from .base import BaseProvider, CompletionResult, ProviderError
from .http_json import DEFAULT_PROVIDER_TIMEOUT_SECONDS, env_float, env_int, post_json


DEFAULT_COMPAT_BASE_URL = "https://api.deepseek.com"
DEFAULT_COMPAT_MODEL = "deepseek-v4-flash"


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        model: str = "",
        *,
        base_url: str = "",
        api_key_env: str = "COMPAT_LLM_API_KEY",
        base_url_env: str = "COMPAT_LLM_BASE_URL",
        model_env: str = "COMPAT_LLM_MODEL",
        label_env: str = "COMPAT_LLM_LABEL",
        max_tokens_env: str = "COMPAT_LLM_MAX_TOKENS",
        temperature_env: str = "COMPAT_LLM_TEMPERATURE",
        thinking_env: str = "COMPAT_LLM_THINKING",
        default_base_url: str = DEFAULT_COMPAT_BASE_URL,
        default_model: str = DEFAULT_COMPAT_MODEL,
        name_prefix: str = "compatible",
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ):
        self.api_key_env = api_key_env
        self.label_env = label_env
        self.temperature_env = temperature_env
        self.thinking_env = thinking_env
        self.name_prefix = name_prefix
        self.model = model or os.getenv(model_env, default_model)
        self.base_url = (base_url or os.getenv(base_url_env) or default_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else env_float(
            "PROVIDER_TIMEOUT_SECONDS",
            DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        )
        self.max_tokens = max_tokens if max_tokens is not None else env_int(max_tokens_env, 1800)

    @property
    def name(self) -> str:
        return f"{self.name_prefix}-{self.model}"

    def is_available(self) -> bool:
        return bool(os.getenv(self.api_key_env, "").strip() and self.base_url)

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
            "temperature": env_float(self.temperature_env, 0.2, minimum=0.0, maximum=2.0),
            "max_tokens": self.max_tokens,
        }
        thinking = _thinking_config(
            model=self.model,
            base_url=self.base_url,
            label=os.getenv(self.label_env, ""),
            thinking_env=self.thinking_env,
        )
        if thinking:
            payload["thinking"] = thinking
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
            model_label=f"{os.getenv(self.label_env, self.name_prefix)}:{response.get('model') or self.model}",
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


def _thinking_config(*, model: str, base_url: str, label: str = "", thinking_env: str = "COMPAT_LLM_THINKING") -> dict[str, str]:
    mode = os.getenv(thinking_env, "").strip().lower()
    if mode in {"enabled", "disabled"}:
        return {"type": mode}
    if mode in {"off", "false", "0", "no"}:
        return {"type": "disabled"}
    if mode in {"on", "true", "1", "yes"}:
        return {"type": "enabled"}
    if mode in {"auto", "default", "provider"}:
        return {}

    provider_hint = " ".join(
        [
            str(model or "").lower(),
            str(base_url or "").lower(),
            str(label or "").strip().lower(),
        ]
    )
    if any(token in provider_hint for token in ("glm", "bigmodel", "zhipu", "z.ai")):
        return {"type": "disabled"}
    return {}


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
