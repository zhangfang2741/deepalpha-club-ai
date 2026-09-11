"""走势展望（延续 vs 转折）测试。

对应缠论「走势分类」框架：下跌趋势末端出现底背驰 → 可能转为上涨（力度最强的
买点结构）；上涨趋势末端顶背驰 → 可能转为下跌；盘整看是否突破中枢。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.chan.divergence import DivergenceResult
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.pivot import Pivot
from app.services.chan.stroke import Stroke


def _mc(idx: int, price: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=price, high=price + 1,
                        low=price - 1, close=price, raw_start=idx, raw_end=idx)


def _fx(kind: str, idx: int, price: float) -> Fractal:
    mid = _mc(idx, price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price), right=_mc(idx + 1, price))


def _stroke(direction: str, idx: int, p0: float, p1: float) -> Stroke:
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, idx * 10, p0), end=_fx(ek, idx * 10 + 5, p1))


def _div(is_div: bool) -> DivergenceResult:
    return DivergenceResult(is_diverged=is_div, type="trend" if is_div else "none",
                            strength="strong" if is_div else "none",
                            area_ratio=0.5 if is_div else 1.0, description="", dif_ratio=0.5)


def _outlook(walk_type, strokes, divergences, merged=None, pivots=None):
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.walk_type = walk_type
    r.strokes = strokes
    r.divergences = divergences
    r.merged_candles = merged or []
    r.stroke_pivots = pivots or []
    return ChanAnalyzer()._compute_trend_outlook(r)


def test_downtrend_with_bottom_divergence_is_reversal_up():
    # 下跌趋势 + 最后一个下降笔底背驰 → 转折向上（最强买点）
    strokes = [_stroke("up", 0, 100, 110), _stroke("down", 1, 110, 90)]
    divs = [_div(False), _div(True)]  # 最后的下降笔背驰
    assert _outlook("down_trend", strokes, divs) == "reversal_up"


def test_downtrend_without_divergence_is_continuation():
    strokes = [_stroke("up", 0, 100, 110), _stroke("down", 1, 110, 90)]
    divs = [_div(False), _div(False)]
    assert _outlook("down_trend", strokes, divs) == "continuation_down"


def test_uptrend_with_top_divergence_is_reversal_down():
    strokes = [_stroke("down", 0, 110, 100), _stroke("up", 1, 100, 120)]
    divs = [_div(False), _div(True)]  # 最后的上升笔顶背驰
    assert _outlook("up_trend", strokes, divs) == "reversal_down"


def test_uptrend_without_divergence_is_continuation():
    strokes = [_stroke("down", 0, 110, 100), _stroke("up", 1, 100, 120)]
    assert _outlook("up_trend", strokes, [_div(False), _div(False)]) == "continuation_up"


def test_consolidation_breakout_up_and_range():
    strokes = [_stroke("up", 0, 100, 110)]
    piv = Pivot(zg=105, zd=95, gg=110, dd=90, start_time="a", end_time="b",
                level="stroke", elements=[])
    # 现价 120 站上 ZG(105) → 向上突破
    assert _outlook("consolidation", strokes, [_div(False)], merged=[_mc(0, 120)], pivots=[piv]) == "breakout_up"
    # 现价 100 在中枢内 → 盘整延续
    assert _outlook("consolidation", strokes, [_div(False)], merged=[_mc(0, 100)], pivots=[piv]) == "range"
    # 现价 80 跌破 ZD(95) → 向下突破
    assert _outlook("consolidation", strokes, [_div(False)], merged=[_mc(0, 80)], pivots=[piv]) == "breakout_down"


def test_no_strokes_is_unclear():
    assert _outlook("none", [], []) == "unclear"
