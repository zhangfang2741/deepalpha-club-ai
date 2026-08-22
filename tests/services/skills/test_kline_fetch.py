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


def _yahoo_payload(rows: list[dict]) -> dict:
    """构造 Yahoo chart 接口的最小返回结构（rows 内可含 None 表示停牌日）。"""
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [r["ts"] for r in rows],
                    "indicators": {
                        "quote": [
                            {
                                "open": [r["open"] for r in rows],
                                "high": [r["high"] for r in rows],
                                "low": [r["low"] for r in rows],
                                "close": [r["close"] for r in rows],
                                "volume": [r.get("volume") for r in rows],
                            }
                        ]
                    },
                }
            ]
        }
    }


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


async def test_fetch_yahoo_parses_and_skips_null_rows(monkeypatch):
    """Yahoo 正常返回：解析 OHLCV，并跳过含 null 的停牌日。"""
    # 2024-01-02 / 2024-01-03（正常），2024-01-04（close=null，应跳过）
    rows = [
        {"ts": 1704153600, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100},
        {"ts": 1704240000, "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 200},
        {"ts": 1704326400, "open": 2.0, "high": None, "low": 1.5, "close": None, "volume": None},
    ]

    def fake_get(url, params=None, timeout=None, headers=None):
        assert "3887.HK" in url  # 港股走 fmp_symbol 形态
        return _FakeResp(200, _yahoo_payload(rows))

    monkeypatch.setattr(kline.httpx, "get", fake_get)

    bars = await kline._fetch_yahoo("3887.HK", "2024-01-01", "2024-01-31", "daily")

    assert len(bars) == 2
    assert bars[0]["time"] == "2024-01-02"
    assert bars[0]["close"] == 1.5
    assert bars[1]["volume"] == 200.0


async def test_fetch_cn_hk_falls_back_to_eastmoney_when_yahoo_unavailable(monkeypatch):
    """Yahoo 网络不可达时应回退东方财富。"""
    async def fake_yahoo(*_args, **_kwargs):
        raise kline._DataSourceUnavailable("connection reset")

    called = {"eastmoney": False}

    async def fake_eastmoney(secid, start, end, freq):
        called["eastmoney"] = True
        assert secid.startswith("116.")  # 港股 secid 前缀
        return [{"time": "2024-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]

    monkeypatch.setattr(kline, "_fetch_yahoo", fake_yahoo)
    monkeypatch.setattr(kline, "_fetch_eastmoney", fake_eastmoney)

    bars = await kline._fetch_cn_hk("03887.HK", "2024-01-01", "2024-01-31", "daily")

    assert called["eastmoney"] is True
    assert len(bars) == 1
