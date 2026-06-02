"""Market-data adapter boundary for future price overlays."""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from typing import Optional


class MarketAdapterError(Exception):
    """Raised when an optional market-data adapter fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Kline:
    open_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class BaseMarketAdapter(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""

    @abc.abstractmethod
    def fetch_klines(self, *, symbol: str, interval: str, start: str, end: str) -> list[Kline]:
        """Fetch klines or raise MarketAdapterError."""


def configured_market_adapter_name() -> str:
    return os.getenv("MARKET_ADAPTER", "").strip().lower()


_ADAPTER_CACHE: dict[str, BaseMarketAdapter] = {}


def get_market_adapter(name: Optional[str] = None) -> Optional[BaseMarketAdapter]:
    adapter_name = (name if name is not None else configured_market_adapter_name()).strip().lower()
    if not adapter_name:
        return None
    if adapter_name in _ADAPTER_CACHE:
        return _ADAPTER_CACHE[adapter_name]
    if adapter_name == "binance":
        from .binance import BinanceMarketAdapter

        adapter = BinanceMarketAdapter()
        _ADAPTER_CACHE[adapter_name] = adapter
        return adapter
    return None
