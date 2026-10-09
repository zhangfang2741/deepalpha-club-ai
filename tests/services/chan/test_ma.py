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


def test_ma_uses_last_raw_bar_of_each_merged_candle():
    """合并 K 线的 time 可能早于它包含的最后一根原始 K 线（缠论选的是极值那根）；
    均线要取最后一根那天的值，最右一根才对应最新价。"""
    from app.api.v1.chan import _ma_out
    from app.services.chan.analyzer import ChanAnalysisResult
    from app.services.chan.fractal import MergedCandle

    bars = _bars([1, 2, 3, 4, 5, 6, 7, 8])  # 01-01 .. 01-08，收盘 = 1..8
    ma = calc_ma(bars, (3,))

    def candle(idx, time, end):
        return MergedCandle(idx=idx, time=time, open=1, high=2, low=0, close=1, raw_start=0, raw_end=0,
                            volume=1.0, end_time=end)

    # 第二根合并 K 线包含 01-04、01-05，缠论选的极值是 01-04，最后一根原始 K 线是 01-05
    r = ChanAnalysisResult(symbol="T", bars_count=8)
    r.ma = ma
    r.merged_candles = [candle(0, "2025-01-03", "2025-01-03"), candle(1, "2025-01-04", "2025-01-05"),
                        candle(2, "2025-01-08", None)]  # 没有 end_time 的（旧数据）退回 time
    out = _ma_out(r)
    assert out.values["3"] == [2.0, 4.0, 7.0]  # 01-05 的 MA3 = (3+4+5)/3 = 4，不是 01-04 的 3


def test_ma_present_even_when_structure_too_weak_to_analyze():
    """单边走势（分型不足）会提前返回；均线仍要有，图上只剩 K 线时也能看均线。"""
    bars = [{"time": f"2025-01-{i + 1:02d}", "open": 10 + i, "high": 11 + i, "low": 9 + i, "close": 10.5 + i,
             "volume": 1.0} for i in range(30)]
    r = ChanAnalyzer().analyze("TEST", bars)
    assert len(r.fractals) < 2 or len(r.strokes) < 3  # 前提：确实提前返回了
    assert r.ma is not None and r.ma.series[5][-1] == pytest.approx(sum(b["close"] for b in bars[-5:]) / 5, abs=1e-3)


@pytest.mark.parametrize("make,freq", [(_decaying_downtrend_bars, "daily"), (lambda: _intraday_bars(days=16), "30min")])
def test_every_candle_end_time_is_found_in_macd_and_indicator_axes(make, freq):
    """客户端（iOS / 网页）按 end_time 到 MACD 的时间轴取值；每根合并 K 线的 end_time（没有就用 time）
    必须都能在 MACD 和各指标的时间轴里找到，否则图上会出现取不到值、被前一根顶替的错位。"""
    r = ChanAnalyzer().analyze("TEST", make(), freq=freq)
    macd_times, ma_times = set(r.macd.times), set(r.ma.times)
    assert r.merged_candles
    for c in r.merged_candles:
        key = c.end_time or c.time
        assert key in macd_times, (freq, key)
        assert key in ma_times, (freq, key)
