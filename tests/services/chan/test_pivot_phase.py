"""中枢生命周期状态机（pivot_phase）测试。

延续 test_trend_outlook.py 的风格：手搭 Stroke/Pivot/DivergenceResult 直接测
build_pivot_phase，不跑完整分析流程。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.divergence import DivergenceResult
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.pivot import Pivot, find_stroke_pivots
from app.services.chan.pivot_phase import build_pivot_phase
from app.services.chan.signals import generate_buy2_signals
from app.services.chan.stroke import Stroke


def _mc(idx: int, price: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=price, high=price + 1,
                         low=price - 1, close=price, raw_start=idx, raw_end=idx)


def _fx(kind: str, idx: int, price: float) -> Fractal:
    mid = _mc(idx, price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price), right=_mc(idx + 1, price))


def _st(direction: str, idx: int, p0: float, p1: float, confirmed: bool = True) -> Stroke:
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, idx * 10, p0), end=_fx(ek, idx * 10 + 5, p1),
                  confirmed=confirmed)


def _chain(*legs: tuple[str, float, float]) -> list[Stroke]:
    """按顺序生成前后相连的一串笔：leg = (direction, p0, p1)。"""
    return [_st(direction, i, p0, p1) for i, (direction, p0, p1) in enumerate(legs)]


def _pivot_from(strokes: list[Stroke], n_absorbed: int, zg: float, zd: float) -> Pivot:
    """把 strokes 的前 n_absorbed 段当作已被中枢吞并的 elements。

    end_time 必须对齐吞并终点（elements[-1].end_time），否则 _post_pivot_strokes
    的时间过滤会和 elements[3:] 的回填重复计入同一批笔。
    """
    elements = strokes[:n_absorbed]
    return Pivot(zg=zg, zd=zd, gg=zg + 2, dd=zd - 2,
                 start_time=elements[0].start_time, end_time=elements[-1].end_time,
                 level="stroke", elements=elements)


def _div(is_div: bool = False) -> DivergenceResult:
    return DivergenceResult(is_diverged=is_div, type="trend" if is_div else "none",
                             strength="strong" if is_div else "none",
                             area_ratio=0.5 if is_div else 1.0, description="", dif_ratio=0.5)


def _result(strokes, stroke_pivots, divergences) -> ChanAnalysisResult:
    r = ChanAnalysisResult(symbol="T", bars_count=len(strokes))
    r.strokes = strokes
    r.stroke_pivots = stroke_pivots
    r.segment_pivots = []
    r.divergences = divergences or [_div(False) for _ in strokes]
    return r


def test_none_when_not_enough_strokes():
    assert build_pivot_phase(_result([], [], [])) is None


def test_none_when_no_pivot_exists():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 80))
    assert build_pivot_phase(_result(strokes, [], [])) is None


def test_pivot_forming_when_only_three_elements():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92))
    pivot = _pivot_from(strokes, 3, zg=98, zd=92)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "pivot_forming"
    assert pp.direction is None
    assert len(pp.checklist) == 2  # 形成中枢(done) + 下一步(pending)，无「当前阶段」行


def test_pivot_oscillating_when_extension_stays_inside_range():
    # 第4段 92->96 全程落在 [90,98] 内，不满足「起点在区间内、终点越界」的突破判据
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92), ("up", 92, 96))
    pivot = _pivot_from(strokes, 4, zg=98, zd=90)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "pivot_oscillating"
    assert pp.direction is None


def test_leaving_when_breakout_crosses_zg_without_retrace_yet():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92), ("up", 92, 110))
    pivot = _pivot_from(strokes, 4, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "leaving"
    assert pp.direction == "up"
    assert len(pp.branches) == 3
    assert {b.outcome for b in pp.branches} == {"type2", "type3", "back_to_range"}


def test_retrace_confirmed_type3_when_retrace_holds_above_zg():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "retrace_confirmed"
    assert pp.direction == "up"
    assert "三买" in pp.phase_label
    assert pp.branches == []


def test_retrace_confirmed_type2_when_retrace_lands_inside_pivot():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 95))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "retrace_confirmed"
    assert "二买" in pp.phase_label


def test_back_to_range_falls_back_to_oscillating():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 85))  # 85 < ZD(91)，反手跌穿对侧
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "pivot_oscillating"
    assert pp.direction is None


def test_divergence_turn_after_retrace_confirmed_with_matching_divergence():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101), ("up", 101, 130))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)  # 第6段（延续笔）不吞并，走 post 的时间过滤
    divs = [_div(False)] * 5 + [_div(True)]  # 第6段（延续的上升笔）出现背驰
    pp = build_pivot_phase(_result(strokes, [pivot], divs))
    assert pp.phase == "divergence_turn"
    assert pp.direction == "up"


def test_stays_retrace_confirmed_without_matching_divergence():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101), ("up", 101, 130))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    divs = [_div(False)] * 6  # 延续笔没有背驰
    pp = build_pivot_phase(_result(strokes, [pivot], divs))
    assert pp.phase == "retrace_confirmed"


def test_cross_check_matches_generate_buy2_signals():
    """交叉验证：pivot_phase 判定出的 outcome 必须和 signals.py 实际产出的信号一致。

    复用 test_signals.py::test_buy2_fires_when_pivot_absorbs_breakout_and_retrace
    同一份真实吞并场景（find_stroke_pivots 产出的真中枢，不是手搭 elements=[]）。
    """
    e0 = _st("down", 0, 100, 90)
    e1 = _st("up", 1, 90, 98)
    e2 = _st("down", 2, 98, 92)
    breakout = _st("up", 3, 92, 110)
    retrace = _st("down", 4, 110, 96)
    strokes = [e0, e1, e2, breakout, retrace]

    pivots = find_stroke_pivots(strokes)
    assert len(pivots) == 1

    sig = generate_buy2_signals(strokes, pivots)
    assert len(sig) == 1 and sig[0].type == "buy2"

    pp = build_pivot_phase(_result(strokes, pivots, []))
    assert pp.phase == "retrace_confirmed"
    assert "二买" in pp.phase_label
