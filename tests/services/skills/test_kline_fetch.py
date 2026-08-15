"""K 线拉取重试逻辑测试（FMP 429 限流退避）"""
import httpx
import pytest

from app.services.skills import kline


class _FakeResp:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


async def test_fetch_fmp_retries_then_succeeds(monkeypatch):
    """前两次 429、第三次成功：应重试并最终返回数据。"""
    import tenacity.nap

    monkeypatch.setattr(kline, "_FMP_KEY", "test-key")
    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda *_: None)

    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return _FakeResp(429)
        return _FakeResp(
            200,
            [{"date": "2024-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}],
        )

    monkeypatch.setattr(kline.httpx, "get", fake_get)

    bars = await kline._fetch_fmp("NVDA", "2024-01-01", "2024-02-01", "daily")

    assert calls["n"] == 3
    assert bars == [
        {"time": "2024-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
    ]


async def test_fetch_fmp_persistent_429_raises_readable_error(monkeypatch):
    """持续 429：重试用尽后抛出可读的中文错误。"""
    import tenacity.nap

    monkeypatch.setattr(kline, "_FMP_KEY", "test-key")
    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda *_: None)

    def fake_get(url, params=None, timeout=None):
        return _FakeResp(429)

    monkeypatch.setattr(kline.httpx, "get", fake_get)

    with pytest.raises(ValueError, match="数据源请求过于频繁"):
        await kline._fetch_fmp("NVDA", "2024-01-01", "2024-02-01", "daily")
