"""缠论买卖点信号回归测试（真实数据端到端）。

用真实标的 FIG（Figma，2025-07 上市）的日线复权数据锁定一个关键回归：
从 ~122 一路跌到 ~50 的底部背驰，必须能识别出「一买」——曾因过度收紧
（一买仅趋势背驰触发 + 过严的趋势/盘整判据）被整段抹掉。
"""
from __future__ import annotations

import pytest

from app.services.chan.analyzer import ChanAnalyzer

# FIG 前复权 OHLC（时间升序，2025-07-31 上市首日起 30 个交易日）
_FIG_OHLC = [
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


def _fig_bars() -> list[dict]:
    return [
        {"time": f"2025-{(i // 20) + 8:02d}-{(i % 20) + 1:02d}",
         "open": o, "high": h, "low": low, "close": c, "volume": 1000}
        for i, (o, h, low, c) in enumerate(_FIG_OHLC)
    ]


def test_fig_bottom_divergence_yields_buy1():
    """FIG 底部背驰应产出一买（回归：过度收紧曾把它整段抹掉）。"""
    result = ChanAnalyzer().analyze("FIG", _fig_bars())
    buy1 = [s for s in result.signals if s.type == "buy1"]
    assert buy1, "FIG 底部背驰应至少产出一个一买信号"
    # 一买应落在跌势末端的低位（远低于起始的百元上方）
    assert min(s.price for s in buy1) < 60


def test_fig_structure_invariants():
    """FIG 上笔首尾相连、方向交替、线段不吞没起点。"""
    result = ChanAnalyzer().analyze("FIG", _fig_bars())
    st = result.strokes
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
    m = MergedCandle(idx=i, time="", open=p, high=p + 1, low=p - 1, close=p, raw_start=i, raw_end=i)
    return m


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


def test_stale_pivot_does_not_fire_signal():
    """旧中枢不得在其后已形成新中枢、价格偶然回到旧带时误触发二/三类信号。

    回归：FIG 8 月价格回到 12 月旧中枢价格带被误判成二卖。
    """
    from app.services.chan.signals import generate_sell2_signals
    pivots = [
        _piv(26.79, 30.26, "2025-12-10", "2026-03-27"),  # 旧中枢
        _piv(19.82, 21.70, "2026-03-27", "2026-08-05"),  # 新中枢（在两者之间形成）
    ]
    # 8 月的笔：跌破 26→24 再反抽 24→28.03（落在旧中枢1带内），但已在新中枢窗口之后
    strokes = [
        _st("down", "2026-08-06", "2026-08-12", 26.0, 24.0),
        _st("up", "2026-08-12", "2026-08-20", 24.0, 28.03),
    ]
    assert generate_sell2_signals(strokes, pivots) == []


def test_signal_fires_within_pivot_leaving_window():
    """离开段窗口内的正常二卖仍应触发（确保上界没有把有效信号也挡掉）。"""
    from app.services.chan.signals import generate_sell2_signals
    pivots = [_piv(26.79, 30.26, "2025-12-10", "2026-03-27")]  # 仅一个中枢，无上界
    strokes = [
        _st("down", "2026-04-01", "2026-04-08", 27.0, 25.0),   # 跌破 ZD
        _st("up", "2026-04-08", "2026-04-15", 25.0, 28.0),     # 反抽落在中枢内
    ]
    sig = generate_sell2_signals(strokes, pivots)
    assert len(sig) == 1 and sig[0].type == "sell2"


def test_buy2_fires_when_pivot_absorbs_breakout_and_retrace():
    """突破+回踩都落回中枢延伸判定的重叠区间，会被 find_stroke_pivots 吞并。

    真实数据里二买用的就是 find_stroke_pivots 产出的中枢，
    不是像上面几个测试那样手搭一个 elements=[] 的假中枢，必须验证这条真实
    集成路径。回归：吞并导致突破笔/回踩笔从未出现在 `_post_pivot_strokes`
    的结果里，二类买卖点因此在真实数据上几乎永远无法触发。
    """
    from app.services.chan.pivot import find_stroke_pivots
    from app.services.chan.signals import generate_buy2_signals

    # 注：_st 用顶/底分型的 high/low（p±1）作端点价，故中枢实际 ZG/ZD 是
    # (99, 91) 而非入参的整数 (98, 92)——下面的边界都按实际值留有余量。
    e0 = _st("down", "T0", "T1", 100, 90)
    e1 = _st("up", "T1", "T2", 90, 98)
    e2 = _st("down", "T2", "T3", 98, 92)
    breakout = _st("up", "T3", "T4", 92, 110)     # 向上突破 ZG≈99
    retrace = _st("down", "T4", "T5", 110, 96)    # 回踩落回中枢区间内 → 二买
    strokes = [e0, e1, e2, breakout, retrace]

    pivots = find_stroke_pivots(strokes)
    assert len(pivots) == 1
    # 突破笔与回踩笔都应被判定为中枢延伸（这是 pivot.py 里符合缠论标准的行为）
    assert breakout in pivots[0].elements and retrace in pivots[0].elements

    sig = generate_buy2_signals(strokes, pivots)
    assert len(sig) == 1 and sig[0].type == "buy2"
    assert sig[0].price == 95


def test_buy3_fires_when_pivot_absorbs_only_breakout():
    """回踩不回中枢（三买）时，突破笔仍会被吞并进 pivot.elements，只有回踩笔留在中枢之外。

    配对逻辑必须能从 pivot.elements 里找回突破笔，不能假设
    它出现在 `_post_pivot_strokes` 返回的列表里。
    """
    from app.services.chan.pivot import find_stroke_pivots
    from app.services.chan.signals import generate_buy3_signals

    # 同上：实际 ZG≈99，回踩端点须严格高于它才算「不回中枢」。
    e0 = _st("down", "T0", "T1", 100, 90)
    e1 = _st("up", "T1", "T2", 90, 98)
    e2 = _st("down", "T2", "T3", 98, 92)
    breakout = _st("up", "T3", "T4", 92, 110)     # 向上突破 ZG≈99
    retrace = _st("down", "T4", "T5", 110, 105)   # 回踩不破 ZG → 三买
    strokes = [e0, e1, e2, breakout, retrace]

    pivots = find_stroke_pivots(strokes)
    assert len(pivots) == 1
    assert breakout in pivots[0].elements
    assert retrace not in pivots[0].elements

    sig = generate_buy3_signals(strokes, pivots)
    assert len(sig) == 1 and sig[0].type == "buy3"
    assert sig[0].price == 104


def _div(strength, area_ratio, dtype="trend"):
    from app.services.chan.divergence import DivergenceResult
    return DivergenceResult(is_diverged=True, type=dtype, strength=strength,
                            area_ratio=area_ratio, description="", dif_ratio=area_ratio)


def test_signal_strength_reflects_divergence_magnitude_not_trend():
    """信号强度只反映背驰幅度，趋势背驰不应把弱背驰(0.9)拔成 strong。"""
    from app.services.chan.signals import generate_buy1_signals, generate_sell1_signals
    up = _st("up", "T0", "T1", 100, 120)
    down = _st("down", "T0", "T1", 120, 100)
    # 弱幅度趋势背驰 → weak
    assert generate_sell1_signals([up], [_div("weak", 0.91)])[0].strength == "weak"
    assert generate_buy1_signals([down], [_div("weak", 0.92)])[0].strength == "weak"
    # 强幅度 → strong
    assert generate_sell1_signals([up], [_div("strong", 0.3)])[0].strength == "strong"


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


def test_buy2_strength_varies_with_margin_not_hardcoded():
    """二类买点不再固定"medium"：贴着 ZD 回踩的余地小，强度应该更低。"""
    from app.services.chan.signals import generate_buy2_signals
    pivot = _piv(90, 110, "T0", "T1")
    e0 = _st("down", "T1", "T2", 108, 92)
    e1 = _st("up", "T2", "T3", 92, 106)
    e2 = _st("down", "T3", "T4", 106, 94)
    breakout = _st("up", "T4", "T5", 94, 116)   # 突破 ZG=110
    retrace = _st("down", "T5", "T6", 116, 92)  # 回踩至 91，贴近 ZD=90，余地小
    strokes = [e0, e1, e2, breakout, retrace]
    sig = generate_buy2_signals(strokes, [pivot])
    assert len(sig) == 1
    assert sig[0].strength == "weak"


def test_buy3_strength_strong_when_pivot_is_segment_level_with_large_margin():
    """线段级中枢 + 回踩拉开足够余地的三买，应该是 strong。

    验证的是"确实按公式算出来落进 strong 档"，而不是像改动前那样硬编码。
    """
    from app.services.chan.signals import generate_buy3_signals
    pivot = _seg_piv(90, 110, "T0", "T1")
    breakout = _st("up", "T4", "T5", 94, 116)     # 突破 ZG=110
    retrace = _st("down", "T5", "T6", 116, 131)   # 回踩至 130，未回中枢，余地大
    strokes = [breakout, retrace]
    sig = generate_buy3_signals(strokes, [pivot])
    assert len(sig) == 1
    assert sig[0].strength == "strong"
