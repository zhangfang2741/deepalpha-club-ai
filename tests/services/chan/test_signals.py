"""缠论买卖点信号测试。

买卖点严格按缠论标准定义：一类 = czsc 力度背驰 + 趋势前提（两个同向不重叠中枢）；
二类 = 一类后第一次回落 / 反弹不破一类极值；三类 = 离开中枢后第一次回落 / 反弹不回中枢。这里测：
1. 端到端：结构不变量成立；
2. 事件 / 结构 → Signal 组装：各类的标准定义、落点、强度、检测时间，文案不暴露第三方库名；
3. 二/三类强度助手（_type23_strength / _margin_ratio）。
"""
from __future__ import annotations

import pytest

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.czsc_signals import BsEvent
from app.services.chan.signals import generate_all_signals
from tests.services.chan.test_czsc_signals import _decaying_downtrend_bars


def _with_rebound(bars: list[dict], n: int = 12, step: float = 3.0, pullback: int = 6) -> list[dict]:
    """在末尾接一段反弹再小幅回落，形成顶分型、让底部那一下降笔走完（买卖点只落在已完成的笔上）。

    只涨不跌没有顶分型，上升笔成不了，底部那一笔就一直是「最后一笔」。
    """
    import datetime as dt
    out, price = list(bars), bars[-1]["close"]
    day = dt.date.fromisoformat(bars[-1]["time"][:10])
    for k in range(1, n + pullback + 1):
        o, c = price, price + (step if k <= n else -step * 0.6)
        out.append({"time": (day + dt.timedelta(days=k)).isoformat(), "open": o, "high": c + 1.0,
                    "low": o - 1.0, "close": c, "volume": 600})
        price = c
    return out


def test_bottom_divergence_yields_buy1():
    """跌势末端缩量衰减（底背驰）、之后反弹让底部那一笔走完 → 应产出一买（回归：一买曾被整段抹掉）。"""
    result = ChanAnalyzer().analyze("DN", _with_rebound(_decaying_downtrend_bars()))
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


def _div(strength, price_ratio, diverged=True):
    from app.services.chan.divergence import DivergenceResult
    return DivergenceResult(is_diverged=diverged, type="trend", strength=strength if diverged else "none",
                            price_ratio=price_ratio, description="", volume_ratio=price_ratio)


def _ev(sig_type, bi_end_time, price, bar_time=None, span=""):
    return BsEvent(type=sig_type, bar_time=bar_time or bi_end_time, bi_end_time=bi_end_time,
                   bi_end_price=price, span=span)


# ---- 事件 → Signal 组装（严格按缠论标准定义） ----
#
# 一类：趋势背驰——之前至少两个同向、区间不重叠的中枢（下跌趋势：后中枢上沿 < 前中枢下沿），
#       且信号落在离开后一个中枢的那段（价格跌破其下沿）；只在盘整里背驰不算一类。
# 二类：一类之后第一次回落 / 反弹，不破一类的极值。
# 三类：离开中枢后第一次回落 / 反弹没有回到中枢。

# 下跌趋势：A(130–140) → B(110–120)，B 上沿 120 < A 下沿 130；上涨趋势镜像
_DOWN_TREND = [_piv(130, 140, "2024-11-01", "2024-11-20"), _piv(110, 120, "2024-12-01", "2024-12-20")]
_UP_TREND = [_piv(60, 70, "2024-11-01", "2024-11-20"), _piv(80, 90, "2024-12-01", "2024-12-20")]
_NO_DIV = _div("none", 1.0, diverged=False)


def test_buy1_lands_on_stroke_end_with_divergence_strength():
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    events = [_ev("buy1", "2025-01-10", 100.0, bar_time="2025-01-12", span="9笔")]
    sig = generate_all_signals(events, [down], [_div("strong", 0.3)], _DOWN_TREND)
    assert len(sig) == 1
    s = sig[0]
    assert (s.type, s.time, s.price, s.strength) == ("buy1", "2025-01-10", 100.0, "strong")
    assert s.divergence is not None and s.divergence.price_ratio == 0.3  # 窗口不足 9 笔时退回该笔自身背驰
    assert "一类买点" in s.description and "czsc" not in s.description.lower()


def test_signal_records_detection_time_separately_from_stroke_end():
    """信号的 time 仍落在笔终点（图上画在那里），detected_time 记录它亮起的那根K线。"""
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    events = [_ev("buy1", "2025-01-10", 100.0, bar_time="2025-01-14", span="9笔")]
    s = generate_all_signals(events, [down], [_div("strong", 0.3)], _DOWN_TREND)[0]
    assert s.time == "2025-01-10"
    assert s.detected_time == "2025-01-14"


def _fst(direction, i, p0, p1, power, volume, length=8):
    """带力度的笔：第 i 笔，时间按下标递增。"""
    st = _st(direction, f"2025-01-{i + 1:02d}", f"2025-01-{i + 2:02d}", p0, p1)
    st.power_price, st.power_volume, st.length = power, volume, length
    return st


def test_buy1_ratios_follow_czsc_benchmark_over_its_span():
    """一买按 czsc 的比较基准算力度比：末笔 vs max(前一个同向笔, 各关键笔均值)。

    9 笔下跌结构：下降笔低点 90→80→70→60→50 逐段创新低（都是关键笔），价差 20、量能 1000；
    末笔价差 8、量能 500、时长 8 → 价差比 8/20=0.40（强，<0.6）、量能比 0.50、时长比 1.00。
    """
    legs, price = [], 110.0
    for i in range(9):
        if i % 2 == 0:
            last = i == 8
            low = 90 - 10 * (i // 2)
            legs.append(_fst("down", i, price, low, 8 if last else 20, 500 if last else 1000))
            price = low
        else:
            legs.append(_fst("up", i, price, price + 12, 12, 800))
            price += 12
    ev = _ev("buy1", legs[-1].end_time, legs[-1].end_price, span="9笔")
    sig = generate_all_signals([ev], legs, [_NO_DIV] * 9, _DOWN_TREND)
    buy1 = [x for x in sig if x.type == "buy1"]
    assert len(buy1) == 1
    s = buy1[0]
    assert s.divergence is not None
    assert (s.divergence.price_ratio, s.divergence.volume_ratio, s.divergence.length_ratio) == (0.4, 0.5, 1.0)
    assert s.strength == "strong"
    assert "0.40" in s.description and "MACD" not in s.description


def test_buy1_without_local_divergence_is_weak_and_has_no_divergence():
    """一类强度只反映背驰幅度：本地背驰度量未确认时降为 weak，不挂背驰对象。"""
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    sig = generate_all_signals([_ev("buy1", "2025-01-10", 100.0)], [down], [_div("none", 1.2, diverged=False)],
                               _DOWN_TREND)
    assert sig[0].strength == "weak"
    assert sig[0].divergence is None


def test_sell1_weak_divergence_not_promoted():
    up = _st("up", "2025-01-01", "2025-01-10", 100, 120)
    sig = generate_all_signals([_ev("sell1", "2025-01-10", 120.0)], [up], [_div("weak", 0.91)], _UP_TREND)
    assert sig[0].strength == "weak"


# ---- 一类：必须是趋势背驰 ----

def test_buy1_without_two_pivots_is_not_type1():
    """只有盘整、没有两个依次下移的中枢：新低 + 力度变弱只是盘整背驰，不算一买。"""
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    ev = [_ev("buy1", "2025-01-10", 100.0)]
    assert generate_all_signals(ev, [down], [_div("strong", 0.3)], []) == []
    assert generate_all_signals(ev, [down], [_div("strong", 0.3)], _DOWN_TREND[1:]) == []


def test_buy1_with_overlapping_pivots_is_not_type1():
    """两个中枢区间重叠（B 上沿 132 ≥ A 下沿 130）：不是下跌趋势。"""
    overlap = [_piv(130, 140, "2024-11-01", "2024-11-20"), _piv(120, 132, "2024-12-01", "2024-12-20")]
    down = _st("down", "2025-01-01", "2025-01-10", 125, 100)
    assert generate_all_signals([_ev("buy1", "2025-01-10", 100.0)], [down], [_div("strong", 0.3)], overlap) == []


def test_buy1_must_leave_the_last_pivot():
    """信号价没跌破后一个中枢的下沿（115 ≥ 110）：还在中枢里，不是离开 B 的那段背驰。"""
    down = _st("down", "2025-01-01", "2025-01-10", 125, 115)
    assert generate_all_signals([_ev("buy1", "2025-01-10", 115.0)], [down], [_div("strong", 0.3)], _DOWN_TREND) == []


def test_sell1_requires_uptrend():
    up = _st("up", "2025-01-01", "2025-01-10", 100, 120)
    assert generate_all_signals([_ev("sell1", "2025-01-10", 120.0)], [up], [_div("strong", 0.3)], _DOWN_TREND) == []
    assert [x.type for x in generate_all_signals([_ev("sell1", "2025-01-10", 120.0)], [up],
                                                  [_div("strong", 0.3)], _UP_TREND)] == ["sell1"]


# ---- 二类：一类之后第一次回落 / 反弹不破一类极值 ----

def _after_buy1(second_low, extra=()):
    """一买（100）→ 反弹到 115（回到 B 里，避免顺带构成三卖）→ 第一次回落到 second_low。

    注：测试笔的端点取分型的极值（比给定价低 / 高 1），断言一律读笔的实际端点价。
    """
    legs = [_st("down", "2025-01-01", "2025-01-10", 120, 100),
            _st("up", "2025-01-10", "2025-01-15", 100, 115),
            _st("down", "2025-01-15", "2025-01-20", 115, second_low), *extra]
    return legs, [_ev("buy1", "2025-01-10", 100.0, span="9笔")]


def test_buy2_is_first_pullback_after_buy1_not_breaking_its_low():
    legs, ev = _after_buy1(103)
    sig = generate_all_signals(ev, legs, [_div("strong", 0.3)] + [_NO_DIV] * 2, _DOWN_TREND,
                               stroke_done_at={"2025-01-20": "2025-01-22"})
    buy2 = [x for x in sig if x.type == "buy2"]
    assert [(x.time, x.price, x.detected_time) for x in buy2] == [("2025-01-20", legs[2].end_price, "2025-01-22")]
    assert "一类买点" in buy2[0].description and "没有跌破" in buy2[0].description


def test_no_buy2_when_pullback_breaks_buy1_low():
    """第一次回落就跌破一买低点：背驰段还在延伸，一买本身也不成立，自然也没有二买。"""
    legs, ev = _after_buy1(98)
    sig = generate_all_signals(ev, legs, [_div("strong", 0.3)] + [_NO_DIV] * 2, _DOWN_TREND)
    assert [x.type for x in sig if x.type in ("buy1", "buy2")] == []


def test_only_first_pullback_counts_as_buy2():
    legs, ev = _after_buy1(103, extra=(_st("up", "2025-01-20", "2025-01-25", 103, 116),
                                       _st("down", "2025-01-25", "2025-01-30", 116, 106)))
    sig = generate_all_signals(ev, legs, [_div("strong", 0.3)] + [_NO_DIV] * 4, _DOWN_TREND)
    assert [(x.type, x.time) for x in sig if x.type == "buy2"] == [("buy2", "2025-01-20")]


def test_buy2_needs_a_standard_buy1_first():
    """没有一买（或一买不满足趋势背驰）就没有二买；czsc 的「支撑重叠」二买事件不再采用。"""
    legs, ev = _after_buy1(103)
    czsc_buy2 = [_ev("buy2", "2025-01-20", 103.0)]
    assert generate_all_signals(czsc_buy2, legs, [_NO_DIV] * 3, _DOWN_TREND) == []
    assert generate_all_signals(ev, legs, [_div("strong", 0.3)] + [_NO_DIV] * 2, []) == []


def test_buy2_carries_no_divergence_object():
    """二类不是背驰信号，不挂背驰对象；强度按信号前最近已结束中枢分档（取值合法即可）。"""
    legs, ev = _after_buy1(103)
    sig = generate_all_signals(ev, legs, [_div("strong", 0.3)] + [_NO_DIV] * 2, _DOWN_TREND)
    buy2 = [x for x in sig if x.type == "buy2"][0]
    assert buy2.divergence is None and buy2.strength in ("weak", "medium", "strong")


# ---- 三类：离开中枢后第一次回落 / 反弹没有回到中枢 ----

_PIVOT = [_piv(90, 100, "2025-01-01", "2025-01-10")]


def test_buy3_when_first_pullback_stays_above_pivot():
    legs = [_st("up", "2025-01-10", "2025-01-15", 95, 115),     # 从中枢内出发、收在上沿 100 之上：离开中枢
            _st("down", "2025-01-15", "2025-01-20", 115, 105)]  # 第一次回落低点 105 > 上沿 100
    sig = generate_all_signals([], legs, [_NO_DIV] * 2, _PIVOT, stroke_done_at={"2025-01-20": "2025-01-21"})
    assert [(x.type, x.time, x.price, x.detected_time) for x in sig] == [
        ("buy3", "2025-01-20", legs[1].end_price, "2025-01-21")]
    assert "没有回到中枢" in sig[0].description


def test_no_buy3_when_pullback_back_inside_then_next_breakout_counts():
    legs = [_st("up", "2025-01-10", "2025-01-15", 95, 115),
            _st("down", "2025-01-15", "2025-01-20", 115, 98),     # 回到中枢里：这次离开不算
            _st("up", "2025-01-20", "2025-01-25", 98, 120),       # 再次离开
            _st("down", "2025-01-25", "2025-01-30", 120, 108)]    # 这次回落守在中枢之上
    sig = generate_all_signals([], legs, [_NO_DIV] * 4, _PIVOT)
    assert [(x.type, x.time) for x in sig] == [("buy3", "2025-01-30")]


def test_sell3_mirror():
    legs = [_st("down", "2025-01-10", "2025-01-15", 95, 80),
            _st("up", "2025-01-15", "2025-01-20", 80, 86)]         # 反弹高点 86 < 下沿 90
    sig = generate_all_signals([], legs, [_NO_DIV] * 2, _PIVOT)
    assert [(x.type, x.price) for x in sig] == [("sell3", legs[1].end_price)]


def test_czsc_type3_events_are_not_used():
    """三类只由结构推出：没有离开中枢的结构，czsc 给的三买事件也不采用。"""
    down = _st("down", "2025-01-25", "2025-02-01", 140, 131)
    assert generate_all_signals([_ev("buy3", "2025-02-01", 131.0)], [down], [_NO_DIV], _PIVOT) == []


def test_buy3_strong_with_segment_pivot_and_large_margin():
    from app.services.chan.pivot import Pivot
    seg = Pivot(zg=110, zd=90, gg=112, dd=88, start_time="2025-01-01", end_time="2025-01-20",
                level="segment", elements=[])
    legs = [_st("up", "2025-01-20", "2025-01-25", 100, 150), _st("down", "2025-01-25", "2025-02-01", 150, 131)]
    sig = generate_all_signals([], legs, [_NO_DIV] * 2, [seg])
    assert [(x.type, x.strength) for x in sig] == [("buy3", "strong")]


def test_latest_pivot_before_ignores_pivot_still_open():
    """信号时刻尚未结束的中枢不参与强度计算（不回看未来）。"""
    from app.services.chan.signals import _latest_pivot_before
    assert _latest_pivot_before([_piv(90, 110, "2025-01-01", "2025-03-01")], "2025-02-01") is None


def test_signals_sorted_deduped_and_localized():
    down = _st("down", "2025-01-01", "2025-01-10", 120, 100)
    events = [_ev("buy1", "2025-01-10", 100.0), _ev("buy1", "2025-01-10", 100.0)]
    sig = generate_all_signals(events, [down], [_div("medium", 0.6)], _DOWN_TREND, lang="en")
    assert [s.type for s in sig] == ["buy1"]
    assert sig[0].label == "1st Buy"
    assert "Type-1 buy" in sig[0].description


def test_event_on_later_extended_stroke_is_dropped():
    """信号所属笔后来被延伸（价格继续创新低/新高），该端点已不在最终结构中 → 视为失效信号丢弃。"""
    final_down = _st("down", "2025-01-01", "2025-01-20", 120, 90)  # 1/10 的低点后又延伸到 1/20
    sig = generate_all_signals([_ev("buy1", "2025-01-10", 100.0)], [final_down], [_NO_DIV], _DOWN_TREND)
    assert sig == []


def test_event_direction_must_match_stroke():
    """买点只能落在下降笔终点、卖点只能落在上升笔终点。"""
    up = _st("up", "2025-01-01", "2025-01-10", 100, 120)
    assert generate_all_signals([_ev("buy1", "2025-01-10", 120.0)], [up], [_NO_DIV], _DOWN_TREND) == []


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


# ---- 回归（DXCM）：一买后价格回到最后一个中枢，中枢被延伸，不能因此否掉一买 ----

def _formed_piv(zd, zg, first3_end, end_time):
    """前三笔在 first3_end 已完成（中枢已形成），但后来被延伸到 end_time 才结束。"""
    from app.services.chan.pivot import Pivot
    els = [_st("down", "2025-10-01", "2025-10-10", zg + 2, zd),
           _st("up", "2025-10-10", "2025-10-20", zd, zg),
           _st("down", "2025-10-20", first3_end, zg, zd + 1)]
    return Pivot(zg=zg, zd=zd, gg=zg + 2, dd=zd - 2, start_time="2025-10-01", end_time=end_time,
                 level="stroke", elements=els)


_A = _piv(83.48, 87.65, "2025-05-20", "2025-08-06")
_B_EXTENDED = _formed_piv(64.67, 69.77, "2025-11-01", "2026-07-16")  # 一买之后被延伸到 7 月


def test_buy1_counts_when_last_pivot_formed_before_but_extended_after():
    """缠论：趋势背驰后价格至少回到最后一个中枢——这正是一买的确认，中枢因此延伸不该否掉一买。"""
    down = _st("down", "2026-04-09", "2026-04-29", 66.4, 56.72)
    sig = generate_all_signals([_ev("buy1", "2026-04-29", 56.72)], [down], [_div("strong", 0.3)], [_A, _B_EXTENDED])
    assert [(s.type, s.time) for s in sig] == [("buy1", "2026-04-29")]


def test_buy1_not_counted_before_last_pivot_formed():
    """后一个中枢还没形成（前三笔未走完）时，不能拿它当趋势前提（不回看未来）。"""
    down = _st("down", "2025-10-20", "2025-10-31", 70, 56.45)
    sig = generate_all_signals([_ev("buy1", "2025-10-31", 56.45)], [down], [_div("strong", 0.3)], [_A, _B_EXTENDED])
    assert sig == []


def test_buy1_broken_by_next_pullback_is_dropped():
    """一买之后下一次回落又创新低：背驰段还在延伸，这个一买不成立，只认最后那个。"""
    legs = [_st("down", "2026-03-19", "2026-04-02", 68.8, 60.57),
            _st("up", "2026-04-02", "2026-04-09", 60.57, 66.4),
            _st("down", "2026-04-09", "2026-04-29", 66.4, 56.72),
            _st("up", "2026-04-29", "2026-06-10", 56.72, 78.9),
            _st("down", "2026-06-10", "2026-06-30", 78.9, 67.3)]
    ev = [_ev("buy1", "2026-04-02", 60.57), _ev("buy1", "2026-04-29", 56.72)]
    sig = generate_all_signals(ev, legs, [_div("strong", 0.3)] * 5, [_A, _B_EXTENDED])
    assert [(s.type, s.time) for s in sig if s.type in ("buy1", "buy2")] == [
        ("buy1", "2026-04-29"), ("buy2", "2026-06-30")]


# ---- 严格定义：买卖点只落在已完成的笔上 ----

def test_no_signal_on_unfinished_last_stroke():
    """最后一笔还在走（端点可能继续延伸、甚至回到中枢），其上的买卖点尚不成立，不输出。"""
    bars = _decaying_downtrend_bars(shrink_volume=False)
    result = ChanAnalyzer().analyze("DN", bars)
    assert result.signals, "合成数据应至少产出一个买卖点"
    last_end = result.strokes[-1].end_time
    assert all(s.confirmed for s in result.signals)
    assert all(s.time != last_end for s in result.signals)
    # 截掉尾部，让某个信号所在的笔变成「最后一笔」：该信号必须随之消失
    sig_time = result.signals[-1].time
    cut = [b for b in bars if b["time"][:10] <= sig_time] + [b for b in bars if b["time"][:10] > sig_time][:1]
    cut_result = ChanAnalyzer().analyze("DN", cut)
    if cut_result.strokes and cut_result.strokes[-1].end_time == sig_time:
        assert sig_time not in {s.time for s in cut_result.signals}


def test_signal_on_unfinished_stroke_becomes_candidate():
    """最后一笔上的信号不算买卖点，但保留为「待确认」候选（供雷达单独展示）。"""
    result = ChanAnalyzer().analyze("DN", _decaying_downtrend_bars())  # 数据停在底部，一买在最后一笔上
    last_end = result.strokes[-1].end_time
    assert all(s.time != last_end for s in result.signals)
    assert any(c.type == "buy1" and c.time == last_end and not c.confirmed for c in result.candidate_signals)
