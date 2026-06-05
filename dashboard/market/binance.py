"""Binance public REST market adapter for optional dashboard overlays."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .base import BaseMarketAdapter, Kline, MarketAdapterError


DEFAULT_BASE_URL = "https://api.binance.com"
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}
ALLOWED_INTERVALS = {"1m": 60, "5m": 300}
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_CACHE_TTL_SECONDS = 600.0
MAX_KLINES = 1000


@dataclass
class _CacheEntry:
    expires_at: float
    klines: list[Kline]


class BinanceMarketAdapter(BaseMarketAdapter):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("BINANCE_SPOT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else _env_float(
            "MARKET_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
        )
        self.cache_ttl_seconds = cache_ttl_seconds if cache_ttl_seconds is not None else _env_float(
            "MARKET_CACHE_TTL_SECONDS",
            DEFAULT_CACHE_TTL_SECONDS,
        )
        self._cache: dict[str, _CacheEntry] = {}
        self._in_flight: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "binance"

    def fetch_klines(self, *, symbol: str, interval: str, start: str, end: str) -> list[Kline]:
        normalized_symbol = normalize_symbol(symbol)
        normalized_interval = normalize_interval(interval)
        start_dt = parse_market_datetime(start, label="start")
        end_dt = parse_market_datetime(end, label="end")
        if end_dt <= start_dt:
            raise MarketAdapterError("end must be later than start")

        interval_seconds = ALLOWED_INTERVALS[normalized_interval]
        start_dt = floor_market_datetime(start_dt, interval_seconds)
        end_dt = ceil_market_datetime(end_dt, interval_seconds)
        estimated = int(((end_dt - start_dt).total_seconds() // interval_seconds) + 1)
        if estimated > MAX_KLINES:
            raise MarketAdapterError(f"window too large for interval {normalized_interval}; max {MAX_KLINES} klines")

        cache_key = (
            f"{self.name}:{normalized_symbol}:{normalized_interval}:"
            f"{format_market_datetime(start_dt)}:{format_market_datetime(end_dt)}"
        )
        event: threading.Event | None = None
        with self._lock:
            cached = self._cache.get(cache_key)
            now = time.time()
            if cached and cached.expires_at > now:
                return list(cached.klines)
            event = self._in_flight.get(cache_key)
            if event is None:
                event = threading.Event()
                self._in_flight[cache_key] = event
                should_fetch = True
            else:
                should_fetch = False

        if not should_fetch:
            event.wait(timeout=max(0.1, self.timeout_seconds) + 1.0)
            with self._lock:
                cached = self._cache.get(cache_key)
                if cached and cached.expires_at > time.time():
                    return list(cached.klines)
            raise MarketAdapterError("binance in-flight request did not populate cache")

        try:
            payload = self._fetch_json(
                "/api/v3/klines",
                {
                    "symbol": normalized_symbol,
                    "interval": normalized_interval,
                    "startTime": str(to_epoch_ms(start_dt)),
                    "endTime": str(to_epoch_ms(end_dt)),
                    "limit": str(min(MAX_KLINES, max(1, estimated))),
                },
            )
            klines = parse_binance_klines(payload)
            with self._lock:
                self._cache[cache_key] = _CacheEntry(
                    time.time() + max(0.0, self.cache_ttl_seconds),
                    klines,
                )
            return list(klines)
        finally:
            with self._lock:
                finished = self._in_flight.pop(cache_key, None)
            if finished:
                finished.set()

    def _fetch_json(self, path: str, params: dict[str, str]) -> Any:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=max(0.1, self.timeout_seconds)) as response:
                status = getattr(response, "status", 200)
                body = response.read().decode("utf-8", "replace")
        except Exception as exc:
            raise MarketAdapterError(f"binance request failed: {type(exc).__name__}: {exc}") from exc
        if status >= 400:
            raise MarketAdapterError(f"binance returned HTTP {status}", status_code=status)
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MarketAdapterError("binance returned invalid JSON") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def normalize_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if normalized not in ALLOWED_SYMBOLS:
        raise MarketAdapterError("unsupported symbol")
    return normalized


def normalize_interval(interval: str) -> str:
    normalized = str(interval or "").strip()
    if normalized not in ALLOWED_INTERVALS:
        raise MarketAdapterError("unsupported interval")
    return normalized


def parse_market_datetime(value: str, *, label: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise MarketAdapterError(f"{label} is required")
    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MarketAdapterError(f"{label} must be YYYY-MM-DD HH:MM[:SS]") from exc
    if parsed.tzinfo:
        return datetime.fromtimestamp(parsed.timestamp())
    return parsed.replace(tzinfo=None)


def format_market_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def floor_market_datetime(value: datetime, interval_seconds: int) -> datetime:
    timestamp = int(value.timestamp())
    floored = timestamp - (timestamp % interval_seconds)
    return datetime.fromtimestamp(floored).replace(microsecond=0)


def ceil_market_datetime(value: datetime, interval_seconds: int) -> datetime:
    timestamp = int(value.timestamp())
    remainder = timestamp % interval_seconds
    ceiled = timestamp if remainder == 0 else timestamp + (interval_seconds - remainder)
    return datetime.fromtimestamp(ceiled).replace(microsecond=0)


def to_epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def parse_binance_klines(payload: Any) -> list[Kline]:
    if not isinstance(payload, list):
        raise MarketAdapterError("binance returned unexpected payload")
    klines = []
    for row in payload:
        if not isinstance(row, list) or len(row) < 6:
            raise MarketAdapterError("binance returned malformed kline row")
        try:
            open_time_ms = int(row[0])
            kline = Kline(
                open_time=datetime.fromtimestamp(open_time_ms / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        except (TypeError, ValueError) as exc:
            raise MarketAdapterError("binance returned invalid kline values") from exc
        klines.append(kline)
    return klines
