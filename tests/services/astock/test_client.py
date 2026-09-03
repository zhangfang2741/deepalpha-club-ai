"""astock 客户端 K 线解析测试（mock 东方财富响应，不发真实请求）。"""

import httpx
import pytest

from app.services.astock import client as astock_client
from app.services.astock.client import (
    AStockDataUnavailable,
    fetch_close_on_or_after,
    fetch_daily_bars,
)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


_SAMPLE = {
    "data": {
        "klines": [
            "2026-01-05,10.00,10.50,10.80,9.90,1000,10500",
            "2026-01-06,10.50,10.20,10.60,10.10,900,9200",
            "2026-01-07,10.20,11.00,11.10,10.15,1200,13000",
        ]
    }
}


async def test_fetch_daily_bars_parses_and_sorts(monkeypatch):
    def fake_get(url, params=None, timeout=None, trust_env=None):
        return _FakeResp(_SAMPLE)

    monkeypatch.setattr(astock_client.httpx, "get", fake_get)
    bars = await fetch_daily_bars("600519", "2026-01-01", "2026-01-10")
    assert [b["date"] for b in bars] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert bars[0]["open"] == 10.00
    assert bars[0]["close"] == 10.50
    assert bars[0]["high"] == 10.80
    assert bars[0]["low"] == 9.90
    assert bars[0]["volume"] == 1000.0


async def test_fetch_daily_bars_empty(monkeypatch):
    monkeypatch.setattr(
        astock_client.httpx, "get", lambda *a, **k: _FakeResp({"data": None})
    )
    bars = await fetch_daily_bars("000001", "2026-01-01", "2026-01-10")
    assert bars == []


async def test_fetch_close_on_or_after_picks_first_ge(monkeypatch):
    monkeypatch.setattr(
        astock_client.httpx, "get", lambda *a, **k: _FakeResp(_SAMPLE)
    )
    # 目标日 2026-01-06 当天有 bar
    bar = await fetch_close_on_or_after("600519", "2026-01-06")
    assert bar is not None
    assert bar["date"] == "2026-01-06"
    # 目标日 2026-01-01 无当日数据，取其后第一个交易日 01-05
    bar2 = await fetch_close_on_or_after("600519", "2026-01-01")
    assert bar2 is not None
    assert bar2["date"] == "2026-01-05"


async def test_transport_error_raises_unavailable(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(astock_client.httpx, "get", boom)
    with pytest.raises(AStockDataUnavailable):
        await fetch_daily_bars("600519", "2026-01-01", "2026-01-10")
