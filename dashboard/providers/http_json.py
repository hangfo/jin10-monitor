"""Small JSON-over-HTTP helper for optional provider adapters."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import ProviderError


DEFAULT_PROVIDER_TIMEOUT_SECONDS = 45.0


def env_float(name: str, default: float, *, minimum: float = 0.1, maximum: float = 300.0) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return max(minimum, min(parsed, maximum))


def env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 32768) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(minimum, min(parsed, maximum))


def post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=max(0.1, timeout_seconds)) as response:
            status = int(getattr(response, "status", 200))
            response_body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise ProviderError(f"provider returned HTTP {exc.code}: {detail}", status_code=exc.code) from exc
    except Exception as exc:
        raise ProviderError(f"provider request failed: {type(exc).__name__}: {exc}") from exc
    if status >= 400:
        raise ProviderError(f"provider returned HTTP {status}", status_code=status)
    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ProviderError("provider returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("provider returned unexpected JSON shape")
    return parsed
