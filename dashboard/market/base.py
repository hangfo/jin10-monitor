"""Market-data adapter boundary for future price overlays."""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from typing import Optional


class MarketAdapterError(Exception):
    """Raised when an optional market-data adapter fails."""


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


def get_market_adapter(name: Optional[str] = None) -> Optional[BaseMarketAdapter]:
    adapter_name = (name if name is not None else configured_market_adapter_name()).strip().lower()
    if not adapter_name:
        return None
    return None
