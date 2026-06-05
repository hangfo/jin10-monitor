import asyncio
import json
import threading
import time
import urllib.parse
from datetime import datetime

import pytest

from dashboard.app import app
from dashboard.market import base
from dashboard.market.binance import (
    BinanceMarketAdapter,
    parse_binance_klines,
    parse_market_datetime,
    to_epoch_ms,
)
from dashboard.market.base import MarketAdapterError


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def sample_binance_payload():
    return [
        [
            1717243200000,
            "67000.1",
            "67100.2",
            "66900.3",
            "67050.4",
            "12.5",
            1717243259999,
            "0",
            1,
            "0",
            "0",
            "0",
        ]
    ]


class FakeRequest:
    def __init__(self, query_string):
        self.query_params = dict(urllib.parse.parse_qsl(query_string))


def market_klines_endpoint():
    for route in app.routes:
        if getattr(route, "path", "") == "/api/market/klines":
            return route.endpoint
    raise AssertionError("/api/market/klines route not found")


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def test_get_market_adapter_returns_binance_singleton(monkeypatch):
    base._ADAPTER_CACHE.clear()
    monkeypatch.setenv("MARKET_ADAPTER", "binance")

    adapter = base.get_market_adapter()

    assert adapter is base.get_market_adapter("binance")
    assert adapter.name == "binance"


def test_binance_adapter_fetches_and_normalizes_klines(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request.full_url, timeout))
        return FakeResponse(sample_binance_payload())

    monkeypatch.setattr("dashboard.market.binance.urllib.request.urlopen", fake_urlopen)
    adapter = BinanceMarketAdapter(base_url="https://example.test", timeout_seconds=2.5, cache_ttl_seconds=60)

    klines = adapter.fetch_klines(
        symbol="btcusdt",
        interval="1m",
        start="2024-06-01 20:00:00",
        end="2024-06-01 20:05:00",
    )

    assert len(klines) == 1
    assert klines[0].open == 67000.1
    assert klines[0].close == 67050.4
    assert captured[0][1] == 2.5
    parsed_url = urllib.parse.urlparse(captured[0][0])
    query = urllib.parse.parse_qs(parsed_url.query)
    assert parsed_url.path == "/api/v3/klines"
    assert query["symbol"] == ["BTCUSDT"]
    assert query["interval"] == ["1m"]
    assert query["limit"] == ["6"]
    assert "startTime" in query
    assert "endTime" in query


def test_binance_adapter_expands_second_precision_window_to_full_klines(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(request.full_url)
        return FakeResponse(sample_binance_payload())

    monkeypatch.setattr("dashboard.market.binance.urllib.request.urlopen", fake_urlopen)
    adapter = BinanceMarketAdapter(base_url="https://example.test", cache_ttl_seconds=60)

    adapter.fetch_klines(
        symbol="BTCUSDT",
        interval="1m",
        start="2024-06-01 20:00:35",
        end="2024-06-01 20:02:05",
    )

    query = urllib.parse.parse_qs(urllib.parse.urlparse(captured[0]).query)
    assert query["startTime"] == [str(to_epoch_ms(datetime(2024, 6, 1, 20, 0, 0)))]
    assert query["endTime"] == [str(to_epoch_ms(datetime(2024, 6, 1, 20, 3, 0)))]
    assert query["limit"] == ["4"]


def test_binance_adapter_keeps_exact_minute_window_count_stable(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(request.full_url)
        return FakeResponse(sample_binance_payload())

    monkeypatch.setattr("dashboard.market.binance.urllib.request.urlopen", fake_urlopen)
    adapter = BinanceMarketAdapter(base_url="https://example.test", cache_ttl_seconds=60)

    adapter.fetch_klines(
        symbol="BTCUSDT",
        interval="1m",
        start="2024-06-01 19:44:00",
        end="2024-06-01 21:44:00",
    )

    query = urllib.parse.parse_qs(urllib.parse.urlparse(captured[0]).query)
    assert query["limit"] == ["121"]


def test_binance_adapter_uses_cache(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(sample_binance_payload())

    monkeypatch.setattr("dashboard.market.binance.urllib.request.urlopen", fake_urlopen)
    adapter = BinanceMarketAdapter(base_url="https://example.test", cache_ttl_seconds=60)

    args = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "start": "2024-06-01 20:00:00",
        "end": "2024-06-01 20:01:00",
    }

    assert adapter.fetch_klines(**args)[0].close == 67050.4
    assert adapter.fetch_klines(**args)[0].close == 67050.4
    assert len(calls) == 1


def test_binance_adapter_deduplicates_concurrent_cache_misses():
    calls = []
    started = threading.Event()

    class SlowAdapter(BinanceMarketAdapter):
        def _fetch_json(self, path, params):
            calls.append((path, params))
            started.set()
            time.sleep(0.05)
            return sample_binance_payload()

    adapter = SlowAdapter(base_url="https://example.test", timeout_seconds=1, cache_ttl_seconds=60)
    args = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "start": "2024-06-01 20:00:00",
        "end": "2024-06-01 20:01:00",
    }
    results = []

    first = threading.Thread(target=lambda: results.append(adapter.fetch_klines(**args)[0].close))
    second = threading.Thread(target=lambda: results.append(adapter.fetch_klines(**args)[0].close))
    first.start()
    assert started.wait(timeout=1)
    second.start()
    first.join(timeout=1)
    second.join(timeout=1)

    assert results == [67050.4, 67050.4]
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("symbol", "interval", "start", "end", "message"),
    [
        ("DOGEUSDT", "1m", "2024-06-01 20:00:00", "2024-06-01 20:01:00", "unsupported symbol"),
        ("BTCUSDT", "15m", "2024-06-01 20:00:00", "2024-06-01 20:01:00", "unsupported interval"),
        ("BTCUSDT", "1m", "", "2024-06-01 20:01:00", "start is required"),
        ("BTCUSDT", "1m", "2024-06-01 20:01:00", "2024-06-01 20:00:00", "end must be later"),
    ],
)
def test_binance_adapter_validates_inputs_without_network(monkeypatch, symbol, interval, start, end, message):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("invalid inputs should not call Binance")

    monkeypatch.setattr("dashboard.market.binance.urllib.request.urlopen", fail_urlopen)
    adapter = BinanceMarketAdapter()

    with pytest.raises(MarketAdapterError, match=message):
        adapter.fetch_klines(symbol=symbol, interval=interval, start=start, end=end)


def test_binance_adapter_wraps_network_errors(monkeypatch):
    def fake_urlopen(request, timeout):
        raise TimeoutError("slow")

    monkeypatch.setattr("dashboard.market.binance.urllib.request.urlopen", fake_urlopen)
    adapter = BinanceMarketAdapter()

    with pytest.raises(MarketAdapterError, match="binance request failed"):
        adapter.fetch_klines(
            symbol="BTCUSDT",
            interval="1m",
            start="2024-06-01 20:00:00",
            end="2024-06-01 20:01:00",
        )


def test_parse_binance_klines_rejects_malformed_payload():
    with pytest.raises(MarketAdapterError, match="unexpected payload"):
        parse_binance_klines({"bad": "shape"})


def test_parse_market_datetime_accepts_iso_and_local_forms():
    assert parse_market_datetime("2024-06-01 20:00:00", label="start") == datetime(2024, 6, 1, 20, 0, 0)
    assert parse_market_datetime("2024-06-01T20:00:00", label="start") == datetime(2024, 6, 1, 20, 0, 0)


def test_market_klines_api_degrades_when_unconfigured(monkeypatch):
    monkeypatch.delenv("MARKET_ADAPTER", raising=False)
    base._ADAPTER_CACHE.clear()

    response = asyncio.run(
        market_klines_endpoint()(
            FakeRequest("symbol=BTCUSDT&start=2024-06-01%2020:00:00&end=2024-06-01%2020:01:00")
        )
    )

    body = response_json(response)
    assert body["ok"] is False
    assert body["error"] == "market adapter not configured"
    assert body["klines"] == []


def test_market_klines_api_uses_configured_binance_adapter(monkeypatch):
    base._ADAPTER_CACHE.clear()
    monkeypatch.setenv("MARKET_ADAPTER", "binance")

    def fake_urlopen(request, timeout):
        return FakeResponse(sample_binance_payload())

    monkeypatch.setattr("dashboard.market.binance.urllib.request.urlopen", fake_urlopen)

    response = asyncio.run(
        market_klines_endpoint()(
            FakeRequest("symbol=BTCUSDT&interval=1m&start=2024-06-01%2020:00:00&end=2024-06-01%2020:01:00")
        )
    )

    body = response_json(response)
    assert body["ok"] is True
    assert body["adapter"] == "binance"
    assert body["klines"][0]["close"] == 67050.4
