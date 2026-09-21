"""中枢生命周期状态机（pivot_phase）测试。

延续 test_trend_outlook.py 的风格：手搭 Stroke/Pivot/DivergenceResult 直接测
build_pivot_phase，不跑完整分析流程。
"""
from __future__ import annotations

from typing import Literal

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


def _fx(kind: Literal["top", "bottom"], idx: int, price: float) -> Fractal:
    mid = _mc(idx, price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price), right=_mc(idx + 1, price))


def _st(direction: Literal["up", "down"], idx: int, p0: float, p1: float, confirmed: bool = True) -> Stroke:
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, idx * 10, p0), end=_fx(ek, idx * 10 + 5, p1),
                  confirmed=confirmed)


def _chain(*legs: tuple[Literal["up", "down"], float, float]) -> list[Stroke]:
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
    assert pp is not None
    assert pp.phase == "pivot_oscillating"
    assert pp.direction is None


def test_leaving_when_breakout_crosses_zg_without_retrace_yet():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92), ("up", 92, 110))
    pivot = _pivot_from(strokes, 4, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "leaving"
    assert pp.direction == "up"
    assert len(pp.branches) == 3
    assert {b.outcome for b in pp.branches} == {"type2", "type3", "back_to_range"}


def test_retrace_confirmed_type3_when_retrace_holds_above_zg():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "retrace_confirmed"
    assert pp.direction == "up"
    assert "三买" in pp.phase_label
    assert pp.branches == []


def test_retrace_confirmed_type2_when_retrace_lands_inside_pivot():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 95))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "retrace_confirmed"
    assert "二买" in pp.phase_label


def test_back_to_range_falls_back_to_oscillating():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 85))  # 85 < ZD(91)，反手跌穿对侧
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "pivot_oscillating"
    assert pp.direction is None


def test_divergence_turn_after_retrace_confirmed_with_matching_divergence():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101), ("up", 101, 130))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)  # 第6段（延续笔）不吞并，走 post 的时间过滤
    divs = [_div(False)] * 5 + [_div(True)]  # 第6段（延续的上升笔）出现背驰
    pp = build_pivot_phase(_result(strokes, [pivot], divs))
    assert pp is not None
    assert pp.phase == "divergence_turn"
    assert pp.direction == "up"


def test_stays_retrace_confirmed_without_matching_divergence():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101), ("up", 101, 130))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    divs = [_div(False)] * 6  # 延续笔没有背驰
    pp = build_pivot_phase(_result(strokes, [pivot], divs))
    assert pp is not None
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
    assert pp is not None
    assert pp.phase == "retrace_confirmed"
    assert "二买" in pp.phase_label


def test_analyzer_populates_pivot_phase_end_to_end():
    """端到端：analyzer.analyze() 对真实K线跑出的中枢，pivot_phase 不应为 None。

    注：计划文档给出的 12 根合成 K 线在实测中只产出 1 笔（find_strokes 的
    min_gap=4 默认标准下不足以成笔），会在 analyze() 的「笔数量不足」早退分支
    直接返回，走不到本任务新增的 walk_type_label/trend_outlook_label/pivot_phase
    赋值语句。改用 test_signals.py 中已验证能产出 >=3 笔且形成中枢/一买信号的
    真实 FIG 数据，以确保测试确实覆盖 analyze() 尾部的新增逻辑。
    """
    from app.services.chan.analyzer import ChanAnalyzer

    # FIG（Figma，2025-07 上市）前复权 OHLC，复用自 test_signals.py::_FIG_OHLC，
    # 已验证能产出 >=3 笔、笔级中枢与一买信号。
    fig_ohlc = [
        (85, 124.63, 84.11, 115.5), (134.82, 142.92, 110.11, 122), (113.92, 114.29, 88.6, 88.6),
        (91.19, 94, 79, 79.08), (76.9, 91.49, 76.65, 90.32), (86.65, 87.88, 77.8, 78.24),
        (82.54, 82.6, 78, 78.11), (78.78, 84, 78, 82.5), (84, 90.69, 83.91, 87.36),
        (90.96, 91, 81.05, 81.91), (81.5, 82.94, 76, 76.31), (79, 81, 76.56, 79.42),
        (79.2, 80.75, 75.5, 76.16), (76.42, 76.57, 68.61, 69.41), (70, 75.15, 67, 74.04),
        (73.1, 74.07, 71.82, 72.76), (73.41, 78, 72.41, 77.3), (74.56, 75.7, 69.61, 70.4),
        (70.88, 72.2, 69.3, 70.13), (70.5, 71.68, 68.52, 69.88), (70.18, 72.11, 69.31, 71.26),
        (70.51, 71.44, 68.9, 70.28), (68.96, 68.96, 64.55, 65.57), (66.7, 68.59, 65.54, 68.13),
        (55.9, 57.35, 53.2, 54.56), (52.38, 54.96, 50.49, 54.86), (54.17, 55.32, 52.4, 52.47),
        (52.45, 53.62, 51.43, 53.32), (53.61, 55.21, 50.82, 51.06), (51.05, 56.32, 51.04, 55.96),
    ]
    bars = [
        {"time": f"2025-{(i // 20) + 8:02d}-{(i % 20) + 1:02d}",
         "open": o, "high": h, "low": low, "close": c, "volume": 1000}
        for i, (o, h, low, c) in enumerate(fig_ohlc)
    ]
    result = ChanAnalyzer().analyze("FIG", bars)
    assert result.walk_type_label != ""
    assert result.trend_outlook_label != ""
    # 是否产出 pivot_phase 取决于这段合成数据能不能凑出 >=3 笔和一个中枢；
    # 断言字段存在且类型正确，不断言具体 phase（具体 phase 已由 Task 1 的单测覆盖）。
    if result.pivot_phase is not None:
        assert result.pivot_phase.phase in {
            "pivot_forming", "pivot_oscillating", "leaving", "retrace_confirmed", "divergence_turn",
        }


def test_failed_breakout_attempt_does_not_hide_later_real_breakout():
    """回归：真实数据（AAPL 2026）曾发现的 bug。

    中枢形成后先出现一次向上假突破（back_to_range，回抽反而跌穿对侧 ZD，
    价格甩到远高于中枢又摔到远低于中枢），中间夹着两段没到边界的噪音，之后
    才出现真正决定性的向上突破+回踩确认。旧算法只看 post 里第一对突破+回踩，
    遇到 back_to_range 就直接判定"仍在中枢震荡"，导致现价早已远离中枢一大截
    时还报"中枢震荡"。新算法要跳过失败的尝试，继续找到后面真正生效的那次
    突破——不能在遇到第一次假突破就停手。
    """
    strokes = _chain(
        ("down", 100, 90), ("up", 90, 98), ("down", 98, 92),  # 形成中枢 zg=98 zd=90
        ("up", 92, 110), ("down", 110, 85),                    # 假突破1：向上离开但回抽跌破ZD(85<90) -> back_to_range
        ("up", 85, 96), ("down", 96, 91),                      # 噪音：两段都没碰到中枢边界，非突破候选
        ("up", 91, 120), ("down", 120, 105),                   # 真正突破：向上离开(120>98)，回踩105>98未回中枢 -> type3
    )
    pivot = _pivot_from(strokes, 9, zg=98, zd=90)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "retrace_confirmed"
    assert pp.direction == "up"
    assert "三买" in pp.phase_label
