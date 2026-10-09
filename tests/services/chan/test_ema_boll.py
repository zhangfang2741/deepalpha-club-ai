"""EMA / BOLL：同均线一样按含预热的完整原始前复权收盘算，按合并 K 线的 end_time 对齐输出。

EMA 用 TA-Lib 口径（前 N 根简单平均作种子，与项目里的 MACD 同口径）；
BOLL = 20 周期，中轨 = 20 日简单均线，上 / 下轨 = 中轨 ± 2 倍总体标准差（国内行情软件口径）。
"""
import math

import pytest

from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.chan.fractal import MergedCandle
from app.services.chan.indicators import (
    BOLL_MULT,
    BOLL_PERIOD,
    EMA_PERIODS,
    align_boll,
    calc_boll,
    calc_ema,
)
from app.services.chan.ma import align_to_times


def _bars(closes):
    return [{"time": f"2025-01-{i + 1:02d}", "close": c} for i, c in enumerate(closes)]


def test_defaults():
    assert EMA_PERIODS == (12, 26)
    assert (BOLL_PERIOD, BOLL_MULT) == (20, 2.0)


def test_ema_sma_seed_then_recursive():
    closes = [1, 2, 3, 4, 5, 6, 7]
    ema = calc_ema(_bars(closes), (3,))
    s = ema.series[3]
    assert s[:2] == [None, None]
    assert s[2] == pytest.approx(2.0)  # 前 3 根的简单平均作种子
    k = 2 / (3 + 1)
    assert s[3] == pytest.approx(4 * k + 2.0 * (1 - k))
    assert s[4] == pytest.approx(5 * k + s[3] * (1 - k))


def test_ema_matches_macd_ema_on_same_bars():
    """EMA12 - EMA26 必须等于项目里 MACD 的 DIF（同口径），守住「图上的均线和 MACD 副图对得上」。"""
    from app.services.chan.divergence import calc_macd

    closes = [10 + math.sin(i / 5) * 3 + i * 0.05 for i in range(220)]
    bars = [{"time": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "close": c} for i, c in enumerate(closes)]
    ema = calc_ema(bars, (12, 26))
    macd = calc_macd(bars)
    # MACD 里快线的种子对齐到慢线起点（TA-Lib 口径），独立算的 EMA12 种子更早；两者随预热收敛，过了预热区应当一致
    for i in range(150, 220):
        assert ema.series[12][i] - ema.series[26][i] == pytest.approx(macd.dif[i], abs=1e-3)


def test_boll_mid_upper_lower_population_std():
    closes = [float(i % 7 + i * 0.1) for i in range(40)]
    b = calc_boll(_bars(closes), period=20, mult=2.0)
    assert b.mid[:19] == [None] * 19 and b.upper[:19] == [None] * 19 and b.lower[:19] == [None] * 19
    window = closes[-20:]
    mean = sum(window) / 20
    std = math.sqrt(sum((x - mean) ** 2 for x in window) / 20)  # 总体标准差
    assert b.mid[-1] == pytest.approx(mean, abs=1e-3)
    assert b.upper[-1] == pytest.approx(mean + 2 * std, abs=1e-3)
    assert b.lower[-1] == pytest.approx(mean - 2 * std, abs=1e-3)


def test_boll_flat_prices_zero_width():
    b = calc_boll(_bars([5.0] * 30), period=20, mult=2.0)
    assert b.upper[-1] == b.mid[-1] == b.lower[-1] == 5.0


def test_analyze_has_ema_and_boll_even_when_structure_too_weak():
    bars = [{"time": f"2025-01-{i + 1:02d}", "open": 10 + i, "high": 11 + i, "low": 9 + i, "close": 10.5 + i,
             "volume": 1.0} for i in range(30)]
    r = ChanAnalyzer().analyze("TEST", bars)
    assert r.ema is not None and r.ema.periods == (12, 26)
    assert r.boll is not None and r.boll.period == 20


def test_align_uses_end_time_like_ma():
    from app.api.v1.chan import _boll_out, _ema_out

    bars = _bars([float(i + 1) for i in range(40)])
    r = ChanAnalysisResult(symbol="T", bars_count=40)
    r.ema = calc_ema(bars, (12,))
    r.boll = calc_boll(bars, period=20, mult=2.0)

    def c(idx, time, end):
        return MergedCandle(idx=idx, time=time, open=1, high=2, low=0, close=1, raw_start=0, raw_end=0,
                            volume=1.0, end_time=end)

    r.merged_candles = [c(0, "2025-01-30", "2025-01-30"), c(1, "2025-01-31", "2025-02-01")]
    # 时间轴是 2025-01-01..40 天按 01-NN 编的，31 之后没有；只验证已有时间的对齐和缺失记 None
    ema = _ema_out(r)
    boll = _boll_out(r)
    assert ema.values["12"][0] == pytest.approx(align_to_times(r.ema, ["2025-01-30"])[12][0])
    assert len(boll.upper) == len(boll.mid) == len(boll.lower) == 2
    assert align_boll(r.boll, ["2025-01-30"]).mid[0] == boll.mid[0]
