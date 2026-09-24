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
    assert seen["start"] == "2026-08-15"  # 结束日前 40 个自然日
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
