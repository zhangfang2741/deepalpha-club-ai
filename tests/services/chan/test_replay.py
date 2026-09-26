"""历史阶段回溯（replay）测试。

延续 test_pivot_phase.py 的风格：手搭 Stroke/Pivot 直接测
truncate_as_of/pivot_phase_as_of，不跑完整分析流程。
"""
from __future__ import annotations

from typing import Literal

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.divergence import DivergenceResult
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.pivot import Pivot
from app.services.chan.replay import pivot_phase_as_of, truncate_as_of
from app.services.chan.stroke import Stroke


def _mc(idx: int, price: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=price, high=price + 1,
                         low=price - 1, close=price, raw_start=idx, raw_end=idx)


def _fx(kind: Literal["top", "bottom"], idx: int, price: float) -> Fractal:
    mid = _mc(idx, price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price), right=_mc(idx + 1, price))


def _st(direction: Literal["up", "down"], idx: int, p0: float, p1: float,
        confirmed: bool = True) -> Stroke:
    sk: Literal["top", "bottom"] = "bottom" if direction == "up" else "top"
    ek: Literal["top", "bottom"] = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, idx * 10, p0), end=_fx(ek, idx * 10 + 5, p1),
                  confirmed=confirmed)


def _chain(*legs: tuple[Literal["up", "down"], float, float]) -> list[Stroke]:
    return [_st(direction, i, p0, p1) for i, (direction, p0, p1) in enumerate(legs)]


def _pivot_from(strokes: list[Stroke], n_absorbed: int, zg: float, zd: float) -> Pivot:
    elements = strokes[:n_absorbed]
    return Pivot(zg=zg, zd=zd, gg=zg + 2, dd=zd - 2,
                 start_time=elements[0].start_time, end_time=elements[-1].end_time,
                 level="stroke", elements=elements)


def _div(is_div: bool = False) -> DivergenceResult:
    return DivergenceResult(is_diverged=is_div, type="trend" if is_div else "none",
                             strength="strong" if is_div else "none",
                             price_ratio=0.5 if is_div else 1.0, description="", volume_ratio=0.5)


def _result(strokes, stroke_pivots) -> ChanAnalysisResult:
    r = ChanAnalysisResult(symbol="T", bars_count=len(strokes))
    r.strokes = strokes
    r.stroke_pivots = stroke_pivots
    r.segment_pivots = []
    r.divergences = [_div(False) for _ in strokes]
    return r


# 完整走势：形成中枢 -> 向上突破，等回踩(type3) -> 三买确认，全程 9 段
_FULL_STROKES = _chain(
    ("down", 100, 90), ("up", 90, 98), ("down", 98, 92),   # 形成中枢 zg=98 zd=90
    ("up", 92, 96),                                          # 延伸（未突破）
    ("down", 96, 91),                                        # 延伸（未突破）
    ("up", 91, 110),                                         # 真正突破 zg(98)
    ("down", 110, 101),                                      # 回踩，101>98未回中枢 -> type3 确认三买
)
_FULL_PIVOT = _pivot_from(_FULL_STROKES, 7, zg=98, zd=90)


def test_truncate_before_pivot_completes_drops_pivot_entirely():
    """中枢最初三段都还没走完时，那个中枢在当时还不存在。"""
    result = _result(_FULL_STROKES, [_FULL_PIVOT])
    truncated = truncate_as_of(result, _FULL_STROKES[1].end_time)  # 只到第2段
    assert truncated.stroke_pivots == []
    assert len(truncated.strokes) == 2


def test_phase_as_of_pivot_just_formed_is_forming():
    result = _result(_FULL_STROKES, [_FULL_PIVOT])
    phase = pivot_phase_as_of(result, _FULL_STROKES[2].end_time)  # 恰好三段formed
    assert phase is not None
    assert phase.phase == "pivot_forming"


def test_phase_as_of_during_extension_is_oscillating():
    result = _result(_FULL_STROKES, [_FULL_PIVOT])
    phase = pivot_phase_as_of(result, _FULL_STROKES[4].end_time)  # 延伸到第5段，未突破
    assert phase is not None
    assert phase.phase == "pivot_oscillating"


def test_phase_as_of_breakout_without_retrace_is_leaving():
    result = _result(_FULL_STROKES, [_FULL_PIVOT])
    phase = pivot_phase_as_of(result, _FULL_STROKES[5].end_time)  # 突破笔刚走完，还没回踩
    assert phase is not None
    assert phase.phase == "leaving"
    assert phase.direction == "up"


def test_phase_as_of_after_retrace_is_confirmed():
    result = _result(_FULL_STROKES, [_FULL_PIVOT])
    phase = pivot_phase_as_of(result, _FULL_STROKES[6].end_time)  # 回踩笔走完，确认三买
    assert phase is not None
    assert phase.phase == "retrace_confirmed"
    assert phase.phase_label == "回落未跌回中枢"


def test_phase_as_of_ignores_signals_after_as_of_time():
    """回放不能偷看未来：回放时点之后才出现的买卖点信号不能让当时的阶段写成「确认三买」。"""
    from app.services.chan.signals import Signal
    result = _result(_FULL_STROKES, [_FULL_PIVOT])
    retrace = _FULL_STROKES[6]
    result.signals = [Signal(type="buy3", time=retrace.end_time, price=retrace.end_price,
                             strength="medium", divergence=None, description="")]
    at_retrace = pivot_phase_as_of(result, retrace.end_time)
    assert at_retrace is not None and at_retrace.phase_label == "确认三买"
    before = pivot_phase_as_of(result, _FULL_STROKES[5].end_time)
    assert before is not None and "确认" not in before.phase_label


def test_different_dates_of_same_stock_give_different_phases():
    """同一只股票的中枢阶段随时间推移而不同。

    这正是信号雷达按信号发生当天回溯阶段（而不是全用"今天"的阶段）的意义所在。
    """
    result = _result(_FULL_STROKES, [_FULL_PIVOT])
    early = pivot_phase_as_of(result, _FULL_STROKES[2].end_time)
    late = pivot_phase_as_of(result, _FULL_STROKES[6].end_time)
    assert early is not None and late is not None
    assert early.phase != late.phase
