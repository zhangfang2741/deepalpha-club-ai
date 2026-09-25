"""次级别编排：拉 30 分钟 K 线 → 缠论分析 → 联动判定（取数用假函数，不打网络）。"""
from __future__ import annotations

from app.services.chan import sub_level_service
from app.services.chan.analyzer import ChanAnalysisResult, Recommendation
from tests.services.chan.test_czsc_adapter import _intraday_bars


def _daily(bias: str) -> ChanAnalysisResult:
    r = ChanAnalysisResult(symbol="T", bars_count=100)
    r.recommendation = Recommendation(action="watch", action_label="技术面偏强", bias=bias)
    return r


async def test_fetches_30min_window_and_builds_verdict(monkeypatch):
    seen = {}

    async def fake_fetch(user_id, symbol, start_date, end_date, freq="daily", *, redis=None):
        seen.update(symbol=symbol, start=start_date, end=end_date, freq=freq)
        return _intraday_bars(days=16)

    monkeypatch.setattr(sub_level_service, "fetch_kline", fake_fetch)
    res = await sub_level_service.analyze_sub_level("AAPL", "2026-09-24", _daily("bullish"))

    assert seen["freq"] == "30min"
    assert seen["start"] == "2026-08-05"  # 结束日前 50 个自然日，与详情页 30min 取数窗口对齐
    assert res.verdict in ("resonance_buy", "resonance_sell", "counter_trend", "waiting")
    assert res.sub_freq == "30min"


async def test_fetch_failure_degrades_to_unavailable(monkeypatch):
    async def boom(*args, **kwargs):
        raise ValueError("数据源暂时不可用")

    monkeypatch.setattr(sub_level_service, "fetch_kline", boom)
    res = await sub_level_service.analyze_sub_level("0700.HK", "2026-09-24", _daily("bullish"))
    assert res.verdict == "unavailable"


async def test_empty_bars_degrade_to_unavailable(monkeypatch):
    async def empty(*args, **kwargs):
        return []

    monkeypatch.setattr(sub_level_service, "fetch_kline", empty)
    res = await sub_level_service.analyze_sub_level("600519.SS", "2026-09-24", _daily("bearish"))
    assert res.verdict == "unavailable"


async def test_weekly_parent_fetches_daily_window(monkeypatch):
    from tests.services.chan.test_czsc_adapter import _trending_bars

    seen = {}

    async def fake_fetch(user_id, symbol, start_date, end_date, freq="daily", *, redis=None):
        seen.update(start=start_date, freq=freq)
        return _trending_bars(200, start_price=100.0, up=True)

    monkeypatch.setattr(sub_level_service, "fetch_kline", fake_fetch)
    res = await sub_level_service.analyze_sub_level("AAPL", "2026-09-24", _daily("bullish"), parent_freq="weekly")
    assert seen["freq"] == "daily"
    assert seen["start"] < "2026-04-01"  # 日线要足够的预热，czsc 才能形成笔与买卖点
    assert res.sub_freq == "daily"


class _MemRedis:
    """get/set(ex) 内存替身。"""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int | None] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttl[key] = ex


def test_canonical_end_clamps_to_server_today():
    """截止日统一到服务器当天：东八区客户端日期领先 UTC 一天时，与雷达用同一个截止日。"""
    from datetime import date

    today = date(2026, 9, 25)
    assert sub_level_service.canonical_end("2026-09-26", today=today) == "2026-09-25"
    assert sub_level_service.canonical_end("2026-09-20", today=today) == "2026-09-20"


def _fake_fetch(calls):
    from tests.services.chan.test_czsc_adapter import _intraday_bars, _trending_bars

    async def fetch(user_id, symbol, start_date, end_date, freq="daily", *, redis=None):
        calls.append((symbol, start_date, end_date, freq))
        return _intraday_bars(days=16) if freq == "30min" else _trending_bars(300, start_price=100.0, up=True)
    return fetch


async def test_radar_and_detail_share_one_verdict(monkeypatch):
    """雷达（600519、不管日期范围）与详情页（600519.SS、用户选的范围）读同一份结论。

    回归：两边各算各的（时刻、日线窗口、截止日都不同）→ 气泡显示共振、点进去不是共振。
    """
    calls: list = []
    monkeypatch.setattr(sub_level_service, "fetch_kline", _fake_fetch(calls))
    redis = _MemRedis()

    radar = await sub_level_service.current_sub_level("600519", "daily", end_date="2026-09-24",
                                                      redis=redis, refresh=True)
    fetched = len(calls)
    detail = await sub_level_service.current_sub_level("600519.SS", "daily", end_date="2026-09-24",
                                                       redis=redis)
    assert len(calls) == fetched, "详情页命中雷达写入的结论缓存，不再重算"
    assert detail.model_dump() == radar.model_dump()
    assert all(ttl == sub_level_service.SUB_LEVEL_CACHE_TTL for ttl in redis.ttl.values())


async def test_parent_window_independent_of_caller_range(monkeypatch):
    """大级别窗口是固定口径（与详情页所选日期范围无关），两次无缓存计算取数区间相同。"""
    calls: list = []
    monkeypatch.setattr(sub_level_service, "fetch_kline", _fake_fetch(calls))
    await sub_level_service.current_sub_level("AAPL", "daily", end_date="2026-09-24", redis=None)
    first = [c for c in calls if c[3] == "daily"]
    calls.clear()
    await sub_level_service.current_sub_level("AAPL", "daily", end_date="2026-09-24", redis=None)
    assert [c for c in calls if c[3] == "daily"] == first


async def test_refresh_recomputes_and_overwrites(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sub_level_service, "fetch_kline", _fake_fetch(calls))
    redis = _MemRedis()
    await sub_level_service.current_sub_level("AAPL", "daily", end_date="2026-09-24", redis=redis)
    n = len(calls)
    await sub_level_service.current_sub_level("AAPL", "daily", end_date="2026-09-24", redis=redis, refresh=True)
    assert len(calls) > n, "refresh 必须重算"
