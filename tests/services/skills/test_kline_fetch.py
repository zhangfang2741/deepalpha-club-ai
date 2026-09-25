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


def test_forward_adjust_scales_ohl_by_ratio():
    """复权价低于原始收盘时，等比回调 open/high/low，close 取 adjClose。"""
    o, h, low_, c = kline._forward_adjust(100.0, 110.0, 90.0, 100.0, 50.0)
    assert c == 50.0
    assert o == pytest.approx(50.0)
    assert h == pytest.approx(55.0)
    assert low_ == pytest.approx(45.0)


def test_forward_adjust_guards_zero_close():
    """close<=0 时原样返回，避免除零。"""
    assert kline._forward_adjust(1.0, 2.0, 0.5, 0.0, 0.0) == (1.0, 2.0, 0.5, 0.0)


async def test_fetch_fmp_uses_dividend_adjusted_fields(monkeypatch):
    """FMP 前复权端点返回 adjOpen/adjHigh/adjLow/adjClose：应取复权字段。"""
    monkeypatch.setattr(kline, "_FMP_KEY", "test-key")

    def fake_get(url, params=None, timeout=None):
        assert "dividend-adjusted" in url  # 走前复权端点
        return _FakeResp(200, [
            {"date": "2024-01-02", "adjOpen": 9.0, "adjHigh": 11.0, "adjLow": 8.0,
             "adjClose": 10.0, "open": 90, "high": 110, "low": 80, "close": 100,
             "volume": 100},
        ])

    monkeypatch.setattr(kline.httpx, "get", fake_get)
    bars = await kline._fetch_fmp("NVDA", "2024-01-01", "2024-02-01", "daily")
    assert bars == [
        {"time": "2024-01-02", "open": 9.0, "high": 11.0, "low": 8.0,
         "close": 10.0, "volume": 100}
    ]


async def test_fetch_yahoo_forward_adjusts_and_removes_dividend_gap(monkeypatch):
    """Yahoo：用 adjclose 前复权回调 OHL，消除除息造成的人为跳空。"""
    # 原始 close 在除息日从 100 跳到 90（10 元分红），adjclose 连续（99->90 等）
    rows = [
        {"ts": 1704153600, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 100},
        {"ts": 1704240000, "open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0, "volume": 100},
    ]
    payload = _yahoo_payload(rows)
    # 注入 adjclose：第一日回调为 90（=90/100*100），第二日 90（除息后无需回调）
    payload["chart"]["result"][0]["indicators"]["adjclose"] = [{"adjclose": [90.0, 90.0]}]

    def fake_get(url, params=None, timeout=None, headers=None):
        return _FakeResp(200, payload)

    monkeypatch.setattr(kline.httpx, "get", fake_get)
    bars = await kline._fetch_yahoo("0700.HK", "2024-01-01", "2024-01-31", "daily")
    assert len(bars) == 2
    # 第一日 close 被前复权到 90，与第二日 90 连续——除息跳空被抹平
    assert bars[0]["close"] == pytest.approx(90.0)
    assert bars[0]["open"] == pytest.approx(90.0)   # 100 * (90/100)
    assert bars[1]["close"] == pytest.approx(90.0)


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


# ---- 30 分钟 K 线（次级别确认）----

async def test_fetch_yahoo_30min_converts_utc_to_exchange_local_time(monkeypatch):
    """Yahoo 分钟线返回 UTC 时间戳：按 meta.gmtoffset 换算成交易所本地 YYYY-MM-DD HH:MM。"""
    # 2026-09-24 01:30 / 02:00 UTC = 香港 09:30 / 10:00
    rows = [
        {"ts": 1790213400, "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100},
        {"ts": 1790215200, "open": 10.5, "high": 11.5, "low": 10.0, "close": 11.0, "volume": 200},
    ]
    payload = _yahoo_payload(rows)
    payload["chart"]["result"][0]["meta"] = {"gmtoffset": 28800}
    seen = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        seen.update(params or {})
        return _FakeResp(200, payload)

    monkeypatch.setattr(kline.httpx, "get", fake_get)
    bars = await kline._fetch_yahoo("0700.HK", "2026-09-01", "2026-09-24", "30min")

    assert seen["interval"] == "30m"
    assert [b["time"] for b in bars] == ["2026-09-24 09:30", "2026-09-24 10:00"]
    assert bars[1]["close"] == 11.0  # 分钟线无 adjclose，不做复权回调


async def test_fetch_fmp_intraday_chunks_range_and_merges(monkeypatch):
    """FMP 30 分钟单次约一个月：40 天按 <=20 天分段请求，合并去重、按时间升序、时间截到分钟。"""
    monkeypatch.setattr(kline, "_FMP_KEY", "test-key")
    calls = []

    def fake_get(url, params=None, timeout=None):
        assert "historical-chart/30min" in url
        calls.append((params["from"], params["to"]))
        # 每段都返回同一根重叠 K 线 + 本段专属一根，验证去重
        return _FakeResp(200, [
            {"date": f"{params['to']} 09:30:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            {"date": "2026-09-10 10:00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        ])

    monkeypatch.setattr(kline.httpx, "get", fake_get)
    bars = await kline._fetch_fmp_intraday("AAPL", "2026-08-15", "2026-09-24")

    assert len(calls) >= 2
    for f, t in calls:
        assert (kline._date(t) - kline._date(f)).days <= 20
    times = [b["time"] for b in bars]
    assert times == sorted(times)
    assert len(times) == len(set(times))
    assert "2026-09-10 10:00" in times


async def test_fetch_eastmoney_30min_uses_klt_30(monkeypatch):
    """东方财富回退源：30 分钟用 klt=30，时间保留到分钟。"""
    seen = {}

    def fake_get(url, params=None, timeout=None, trust_env=None):
        seen.update(params)
        return _FakeResp(200, {"data": {"klines": ["2026-09-24 10:00,10,11,12,9,100,1000"]}})

    monkeypatch.setattr(kline.httpx, "get", fake_get)
    bars = await kline._fetch_eastmoney("1.600519", "2026-09-01", "2026-09-24", "30min")

    assert seen["klt"] == "30"
    assert bars[0]["time"] == "2026-09-24 10:00"


async def test_fetch_kline_us_30min_routes_to_fmp_intraday(monkeypatch):
    """美股 30 分钟走 FMP 分钟线分段拉取，而不是日线端点。"""
    async def fake_intraday(symbol, start, end):
        return [{"time": "2026-09-24 09:30", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1}]

    monkeypatch.setattr(kline, "_fetch_fmp_intraday", fake_intraday)
    bars = await kline.fetch_kline(None, "AAPL", "2026-09-01", "2026-09-24", "30min")
    assert bars[0]["time"] == "2026-09-24 09:30"


async def test_fetch_kline_use_cache_false_skips_read_but_writes_fresh(monkeypatch):
    """详情页现拉现算：use_cache=False 不读缓存（拿到盘中最新K线），但新数据照样写回缓存供雷达复用。"""
    from tests.services.chan.test_sub_level_service import _MemRedis

    fresh = [{"time": "2026-09-25 10:30", "open": 1, "high": 2, "low": 0.5, "close": 1.9, "volume": 1}]

    async def fake_intraday(symbol, start, end):
        return fresh

    monkeypatch.setattr(kline, "_fetch_fmp_intraday", fake_intraday)
    redis = _MemRedis()
    key = kline._cache_key(None, "AAPL", "2026-09-01", "2026-09-25", "30min")
    stale = [{"time": "2026-09-24 15:30", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
    await kline.set_json(redis, key, stale, expire=600)

    assert await kline.fetch_kline(None, "AAPL", "2026-09-01", "2026-09-25", "30min", redis=redis) == stale
    got = await kline.fetch_kline(None, "AAPL", "2026-09-01", "2026-09-25", "30min", redis=redis, use_cache=False)
    assert got == fresh
    assert await kline.get_json(redis, key) == fresh  # 写回了新数据
