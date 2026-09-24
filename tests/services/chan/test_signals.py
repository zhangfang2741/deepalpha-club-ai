"""缠论买卖点信号测试。

买卖点是否成立由 czsc 结构信号判定（见 czsc_signals.scan_bs_events），这里测：
1. 端到端：跌势末端缩量衰减（底背驰）能产出一买，结构不变量成立；
2. 事件 → Signal 组装：落点取所属笔终点、一类强度取该笔背驰幅度、
   二/三类强度取信号前最近中枢的级别与余量，文案不暴露第三方库名；
3. 二/三类强度助手（_type23_strength / _margin_ratio）。
"""
from __future__ import annotations

import pytest

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.czsc_signals import BsEvent
from app.services.chan.signals import generate_all_signals
from tests.services.chan.test_czsc_signals import _decaying_downtrend_bars


def test_bottom_divergence_yields_buy1():
    """跌势末端缩量衰减（底背驰）应产出一买（回归：一买曾被整段抹掉）。"""
    result = ChanAnalyzer().analyze("DN", _decaying_downtrend_bars())
    assert len(result.strokes) >= 10, "合成数据应产出足够多的笔"
    buy1 = [s for s in result.signals if s.type == "buy1"]
    assert buy1, "底背驰应至少产出一个一买信号"
    assert min(s.price for s in buy1) < 120
    # 买卖点落在笔端点上（与图上的笔对齐）
    stroke_ends = {s.end_time for s in result.strokes}
    assert all(s.time in stroke_ends for s in result.signals)


def test_structure_invariants_end_to_end():
    """端到端：笔首尾相连、方向交替、线段不吞没起点。"""
    result = ChanAnalyzer().analyze("DN", _decaying_downtrend_bars())
    st = result.strokes
    assert len(st) >= 10
    for a, b in zip(st, st[1:], strict=False):
        assert a.end is b.start
        assert a.direction != b.direction
    for seg in result.segments:
        origin = seg.strokes[0].start_price
        if seg.direction == "up":
            assert seg.low >= origin - 1e-6
        else:
            assert seg.high <= origin + 1e-6


def _mc(i, p):
    from app.services.chan.fractal import MergedCandle
    return MergedCandle(idx=i, time="", open=p, high=p + 1, low=p - 1, close=p, raw_start=i, raw_end=i)


def _fx(kind, i, p, t):
    from app.services.chan.fractal import Fractal
    m = _mc(i, p)
    m.time = t
    return Fractal(type=kind, candle=m, left=_mc(i - 1, p), right=_mc(i + 1, p))


def _st(direction, t0, t1, p0, p1):
    from app.services.chan.stroke import Stroke
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, 0, p0, t0), end=_fx(ek, 2, p1, t1))


def _piv(zd, zg, t0, t1):
    from app.services.chan.pivot import Pivot
    return Pivot(zg=zg, zd=zd, gg=zg + 2, dd=zd - 2, start_time=t0, end_time=t1,
                 level="stroke", elements=[])


def _div(strength, area_ratio, diverged=True):
    from app.services.chan.divergence import DivergenceResult
    return DivergenceResult(is_diverged=diverged, type="trend", strength=strength if diverged else "none",
                            area_ratio=area_ratio, description="", dif_ratio=area_ratio)


def _ev(sig_type, bi_end_time, price, bar_time=None, span=""):
    return BsEvent(type=sig_type, bar_time=bar_time or bi_end_time, bi_end_time=bi_end_time,
                   bi_end_price=price, span=span)


# ---- 事件 → Signal 组装 ----

def test_buy1_lands_on_stroke_end_with_divergence_strength():
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    events = [_ev("buy1", "2025-01-10", 100.0, bar_time="2025-01-12", span="9笔")]
    sig = generate_all_signals(events, [down], [_div("strong", 0.3)], [])
    assert len(sig) == 1
    s = sig[0]
    assert (s.type, s.time, s.price, s.strength) == ("buy1", "2025-01-10", 100.0, "strong")
    assert s.divergence is not None and s.divergence.area_ratio == 0.3
    assert "一类买点" in s.description and "9笔" in s.description
    assert "czsc" not in s.description.lower()


def test_buy1_without_local_divergence_is_weak_and_has_no_divergence():
    """一类强度只反映背驰幅度：本地背驰度量未确认时降为 weak，不挂背驰对象。"""
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    sig = generate_all_signals([_ev("buy1", "2025-01-10", 100.0)], [down], [_div("none", 1.2, diverged=False)], [])
    assert sig[0].strength == "weak"
    assert sig[0].divergence is None


def test_sell1_weak_divergence_not_promoted():
    up = _st("up", "2025-01-01", "2025-01-10", 100, 120)
    sig = generate_all_signals([_ev("sell1", "2025-01-10", 120.0)], [up], [_div("weak", 0.91)], [])
    assert sig[0].strength == "weak"


def test_buy2_strength_uses_latest_pivot_before_signal():
    """二买强度取信号之前最近结束的中枢；贴着 ZD 回踩、笔级中枢 → weak。"""
    pivots = [_piv(90, 110, "2025-01-01", "2025-01-20")]
    down = _st("down", "2025-01-25", "2025-02-01", 108, 91)
    sig = generate_all_signals([_ev("buy2", "2025-02-01", 91.0)], [down], [_div("none", 1.0, diverged=False)], pivots)
    assert sig[0].type == "buy2" and sig[0].strength == "weak"
    assert sig[0].divergence is None


def test_buy3_strong_with_segment_pivot_and_large_margin():
    from app.services.chan.pivot import Pivot
    seg = Pivot(zg=110, zd=90, gg=112, dd=88, start_time="2025-01-01", end_time="2025-01-20",
                level="segment", elements=[])
    down = _st("down", "2025-01-25", "2025-02-01", 140, 131)
    sig = generate_all_signals([_ev("buy3", "2025-02-01", 131.0)], [down], [_div("none", 1.0, diverged=False)], [seg])
    assert sig[0].strength == "strong"


def test_pivot_ending_after_signal_is_ignored():
    """信号时刻尚未结束的中枢不能参与强度计算（不回看未来）→ 无中枢可依时为 weak。"""
    pivots = [_piv(90, 110, "2025-01-01", "2025-03-01")]
    up = _st("up", "2025-01-25", "2025-02-01", 70, 80)
    sig = generate_all_signals([_ev("sell3", "2025-02-01", 80.0)], [up], [_div("none", 1.0, diverged=False)], pivots)
    assert sig[0].strength == "weak"


def test_signals_sorted_deduped_and_localized():
    events = [
        _ev("sell2", "2025-03-01", 120.0),
        _ev("buy1", "2025-01-10", 100.0),
        _ev("buy1", "2025-01-10", 100.0),
    ]
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    up = _st("up", "2025-02-20", "2025-03-01", 100, 120)
    sig = generate_all_signals(events, [down, up], [_div("medium", 0.6), _div("none", 1.0, diverged=False)], [], lang="en")
    assert [s.type for s in sig] == ["buy1", "sell2"]
    assert sig[0].label == "1st Buy"
    assert "Type-1 buy" in sig[0].description


def test_event_on_later_extended_stroke_is_dropped():
    """信号所属笔后来被延伸（价格继续创新低/新高），该端点已不在最终结构中 → 视为失效信号丢弃。"""
    final_down = _st("down", "2025-01-01", "2025-01-20", 120, 90)  # 1/10 的低点后又延伸到 1/20
    events = [_ev("buy1", "2025-01-10", 100.0), _ev("buy2", "2025-01-20", 90.0)]
    sig = generate_all_signals(events, [final_down], [_div("none", 1.0, diverged=False)], [])
    assert [(s.type, s.time) for s in sig] == [("buy2", "2025-01-20")]


def test_event_direction_must_match_stroke():
    """买点只能落在下降笔终点、卖点只能落在上升笔终点。"""
    up = _st("up", "2025-01-01", "2025-01-10", 100, 120)
    sig = generate_all_signals([_ev("buy2", "2025-01-10", 120.0)], [up], [_div("none", 1.0, diverged=False)], [])
    assert sig == []


# ---- 二/三类买卖点强度：中枢级别 + 回踩/反抽余地加权 ----

def _seg_piv(zd, zg, t0, t1):
    from app.services.chan.pivot import Pivot
    return Pivot(zg=zg, zd=zd, gg=zg + 2, dd=zd - 2, start_time=t0, end_time=t1,
                 level="segment", elements=[])


def test_type23_strength_weak_for_stroke_pivot_touching_boundary():
    """笔级中枢、回踩贴着边界（余地≈0）→ weak。"""
    from app.services.chan.signals import _type23_strength
    pivot = _piv(90, 110, "T0", "T1")
    assert _type23_strength(pivot, 0.0) == "weak"


def test_type23_strength_medium_for_segment_pivot_touching_boundary():
    """线段级中枢即便回踩贴着边界，也不该被打成 weak。

    中枢级别本身的权重已经比笔级高一档，最低也是 medium。
    """
    from app.services.chan.signals import _type23_strength
    pivot = _seg_piv(90, 110, "T0", "T1")
    assert _type23_strength(pivot, 0.0) == "medium"


def test_type23_strength_strong_for_stroke_pivot_with_full_margin():
    """笔级中枢但回踩/反抽拉开了一整个中枢高度的余地，也能到 strong。"""
    from app.services.chan.signals import _type23_strength
    pivot = _piv(90, 110, "T0", "T1")
    assert _type23_strength(pivot, 1.0) == "strong"


def test_type23_strength_strong_for_segment_pivot_with_full_margin():
    """线段级中枢 + 满余地，理应是最强的组合。"""
    from app.services.chan.signals import _type23_strength
    pivot = _seg_piv(90, 110, "T0", "T1")
    assert _type23_strength(pivot, 1.0) == "strong"


def test_margin_ratio_normalizes_by_pivot_height():
    from app.services.chan.signals import _margin_ratio
    pivot = _piv(90, 100, "T0", "T1")  # height=10
    assert _margin_ratio(pivot, 90, 95) == pytest.approx(0.5)
    assert _margin_ratio(pivot, 100, 110) == pytest.approx(1.0)


def test_margin_ratio_zero_height_pivot_returns_zero():
    """中枢高度异常（zg==zd）时不能除零，退回 0。"""
    from app.services.chan.pivot import Pivot
    from app.services.chan.signals import _margin_ratio
    pivot = Pivot(zg=100, zd=100, gg=102, dd=98, start_time="T0", end_time="T1",
                  level="stroke", elements=[])
    assert _margin_ratio(pivot, 100, 105) == 0.0
