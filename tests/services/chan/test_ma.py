"""均线（MA）：按原始前复权收盘算简单移动平均，再对齐到合并 K 线，供 App 主图叠加。

日线 5 / 20 / 60，30 分钟同组，周线 5 / 10 / 20。warmup 里的 K 线参与计算、不显示，
所以显示区第一根起就有值（不会前 59 根空着）。
"""
import pytest

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.ma import MA_PERIODS, align_to_times, calc_ma
from tests.services.chan.test_czsc_adapter import _intraday_bars
from tests.services.chan.test_czsc_signals import _decaying_downtrend_bars


def _bars(closes, start=1):
    return [{"time": f"2025-01-{start + i:02d}", "close": c} for i, c in enumerate(closes)]


def test_periods_per_freq():
    assert MA_PERIODS["daily"] == (5, 20, 60)
    assert MA_PERIODS["30min"] == (5, 20, 60)
    assert MA_PERIODS["weekly"] == (5, 10, 20)


def test_calc_ma_is_simple_average_and_none_until_enough_bars():
    ma = calc_ma(_bars([1, 2, 3, 4, 5, 6]), (3, 5))
    assert ma.series[3] == [None, None, 2.0, 3.0, 4.0, 5.0]
    assert ma.series[5] == [None, None, None, None, 3.0, 4.0]
    assert ma.times == [f"2025-01-{d:02d}" for d in range(1, 7)]


def test_calc_ma_fewer_bars_than_period_all_none():
    assert calc_ma(_bars([1, 2]), (5,)).series[5] == [None, None]


def test_align_to_times_picks_same_time_and_none_when_missing():
    ma = calc_ma(_bars([1, 2, 3, 4, 5, 6]), (3,))
    out = align_to_times(ma, ["2025-01-03", "2025-01-06", "2025-02-01"])
    assert out[3] == [2.0, 5.0, None]


def test_analyze_ma_aligned_to_merged_candles_and_uses_warmup():
    """按原始 K 线下标判断：第 60 根起才有 MA60；显示区起点之前的预热 K 线也参与了平均。"""
    bars = _decaying_downtrend_bars()
    r = ChanAnalyzer().analyze("TEST", bars, visible_from=bars[80]["time"])
    assert r.ma is not None and r.ma.periods == (5, 20, 60)
    candles = r.merged_candles
    pos = {b["time"]: i for i, b in enumerate(bars)}
    ma60 = align_to_times(r.ma, [c.time for c in candles])[60]
    assert len(ma60) == len(candles)
    for c, v in zip(candles, ma60, strict=True):
        i = pos[c.time]
        if i < 59:
            assert v is None
        else:
            expect = sum(b["close"] for b in bars[i - 59:i + 1]) / 60
            assert v == pytest.approx(expect, abs=1e-3)
    assert any(pos[c.time] >= 59 for c in candles)  # 确实覆盖到了有值的部分


def test_analyze_weekly_uses_weekly_periods():
    bars = _decaying_downtrend_bars()
    r = ChanAnalyzer().analyze("TEST", bars, freq="weekly")
    assert r.ma is not None and r.ma.periods == (5, 10, 20)


def test_intraday_candle_times_match_bar_times():
    """30 分钟线：合并 K 线的时间字符串必须能在 MA 的时间轴里找到（带时分的格式一致）。"""
    bars = _intraday_bars(days=16)
    r = ChanAnalyzer().analyze("TEST", bars, freq="30min")
    assert r.ma is not None
    got = align_to_times(r.ma, [c.time for c in r.merged_candles])[5]
    assert sum(v is None for v in got) <= 4  # 只有最开头不足 5 根的才允许缺


def test_api_returns_ma_aligned_with_merged_candles():
    from unittest.mock import AsyncMock, patch

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1 import chan as chan_api
    from app.api.v1.auth import get_current_user
    from app.cache.client import get_redis

    app = FastAPI()
    app.include_router(chan_api.router, prefix="/chan")
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": 1})()
    app.dependency_overrides[get_redis] = lambda: None
    with patch.object(chan_api, "fetch_kline", AsyncMock(return_value=_decaying_downtrend_bars())):
        r = TestClient(app).get("/chan/analysis", params={
            "symbol": "AAPL", "start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200
    body = r.json()
    assert body["ma"]["periods"] == [5, 20, 60]
    n = len(body["merged_candles"])
    assert all(len(body["ma"]["values"][k]) == n for k in ("5", "20", "60"))
    assert any(v is not None for v in body["ma"]["values"]["5"])
