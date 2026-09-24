"""中枢生命周期状态机（pivot_phase）测试。

延续 test_trend_outlook.py 的风格：手搭 Stroke/Pivot/DivergenceResult 直接测
build_pivot_phase，不跑完整分析流程。
"""
from __future__ import annotations

from typing import Literal

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.divergence import DivergenceResult
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.pivot import Pivot, _find_pivots_from_elements
from app.services.chan.pivot_phase import build_pivot_phase
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


def test_retrace_inside_absorbing_pivot_is_retrace_confirmed():
    """真实吞并场景：突破笔 + 回踩笔被中枢算法吞并进 elements，阶段应判为回踩确认。

    用中枢算法产出的真中枢（不是手搭 elements=[]），覆盖 _post_pivot_strokes
    把吞并段接回来的逻辑。买卖点标记已改由 czsc 结构信号判定，这里只验证阶段判定本身。
    """
    e0 = _st("down", 0, 100, 90)
    e1 = _st("up", 1, 90, 98)
    e2 = _st("down", 2, 98, 92)
    breakout = _st("up", 3, 92, 110)
    retrace = _st("down", 4, 110, 96)
    strokes = [e0, e1, e2, breakout, retrace]

    pivots = _find_pivots_from_elements(strokes, level="stroke")
    assert len(pivots) == 1

    pp = build_pivot_phase(_result(strokes, pivots, []))
    assert pp is not None
    assert pp.phase == "retrace_confirmed"
    assert "二买" in pp.phase_label


def test_analyzer_populates_pivot_phase_end_to_end():
    """端到端：analyzer.analyze() 对能成笔的K线跑出中枢时，尾部字段应被填充。

    注：原版用 FIG 上市初 30 根真实数据，但 czsc 成笔确认门槛更严、只产出
    1 笔，会在「笔数量不足」早退分支返回，走不到尾部的
    walk_type_label/trend_outlook_label/pivot_phase 赋值。改用
    test_signals.py 的「净向下锯齿」合成数据（已验证 czsc 下 >=10 笔、
    4 个笔级中枢），确保覆盖 analyze() 尾部逻辑。
    """
    from app.services.chan.analyzer import ChanAnalyzer
    from tests.services.chan.test_signals import _decaying_downtrend_bars

    result = ChanAnalyzer().analyze("DN", _decaying_downtrend_bars())
    assert len(result.strokes) >= 10
    assert result.walk_type_label != ""
    assert result.trend_outlook_label != ""
    # 是否产出 pivot_phase 取决于数据能否凑出中枢；断言字段类型正确，
    # 不断言具体 phase（具体 phase 已由上面的单测覆盖）。
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


def test_confirmed_pair_superseded_by_later_opposite_breakout():
    """回归：真实数据（NVDA 2026）发现的 bug。

    「二买」confirmed 之后（回踩落在中枢内），价格反手向下真正突破并确认
    「三卖」，说明更早那次二买判断已经被后续走势推翻了。旧算法找到第一对
    配对就不再往后看，会一直停留在过时的"确认二买"，即便现价早已在中枢
    下方。新算法要继续扫描到 post 结束，用最新出现的决定性状态覆盖更早
    的结论。
    """
    strokes = _chain(
        ("down", 100, 90), ("up", 90, 98), ("down", 98, 92),  # 形成中枢 zg=98 zd=90
        ("up", 92, 110), ("down", 110, 95),                    # 向上突破+回踩：95落在中枢内 -> type2 确认二买
        ("up", 95, 97),                                         # 噪音：97未过zg(98)，不构成突破
        ("down", 97, 80), ("up", 80, 85),                       # 反手向下真突破，回踩85<zd(90)未回中枢 -> type3，覆盖二买
    )
    pivot = _pivot_from(strokes, 8, zg=98, zd=90)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "retrace_confirmed"
    assert pp.direction == "down"
    assert "三卖" in pp.phase_label


def test_open_breakout_at_tail_supersedes_earlier_confirmed_pair():
    """回归：确认配对之后如果 post 以一个新的、还没等到回踩笔的突破收尾。

    应该报告"进行中的突破"（leaving），而不是停留在更早那次已确认的配对。
    """
    strokes = _chain(
        ("down", 100, 90), ("up", 90, 98), ("down", 98, 92),   # 形成中枢 zg=98 zd=90
        ("up", 92, 110), ("down", 110, 105),                    # type3 确认三买
        ("up", 105, 130), ("down", 130, 80),                     # 反手向下突破zd(90)，还没等到回踩笔
    )
    pivot = _pivot_from(strokes, 7, zg=98, zd=90)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "leaving"
    assert pp.direction == "down"
