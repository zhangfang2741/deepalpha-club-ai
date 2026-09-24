"""缠论背驰测试：力度口径（与 czsc 一类买卖点同一口径）+ 趋势/盘整分类。

背驰 = 价格创新高/新低，价差力度弱于前一个同向段，且量能或时长至少一项也更弱。
趋势/盘整：当前段之前已形成 >=2 个中枢为趋势背驰，否则盘整背驰。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.chan.divergence import (
    _in_consolidation,
    check_divergence,
    find_segment_divergences,
    find_stroke_divergences,
)
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.segment import Segment
from app.services.chan.stroke import Stroke


@dataclass
class _Leg:
    start_time: str
    end_time: str


@dataclass
class _Pivot:
    start_time: str
    end_time: str


def test_trend_when_two_or_more_pivots():
    prev_leg = _Leg("2024-01-01", "2024-01-05")
    cur_leg = _Leg("2024-03-01", "2024-03-05")
    # 当前段之前已形成 2 个中枢 → 趋势背驰（非盘整）
    pivots = [_Pivot("2024-01-10", "2024-01-25"), _Pivot("2024-02-05", "2024-02-20")]
    assert _in_consolidation(prev_leg, cur_leg, pivots) is False


def test_consolidation_when_single_pivot():
    prev_leg = _Leg("2024-01-01", "2024-01-05")
    cur_leg = _Leg("2024-02-01", "2024-02-05")
    # 只有单一中枢 → 盘整背驰
    pivots = [_Pivot("2024-01-10", "2024-01-25")]
    assert _in_consolidation(prev_leg, cur_leg, pivots) is True


def test_pivots_after_current_leg_do_not_count():
    prev_leg = _Leg("2024-01-01", "2024-01-05")
    cur_leg = _Leg("2024-01-20", "2024-01-25")
    # 两个中枢中有一个在当前段起点之后形成，不计入 → 仍为盘整
    pivots = [_Pivot("2024-01-10", "2024-01-15"), _Pivot("2024-02-01", "2024-02-10")]
    assert _in_consolidation(prev_leg, cur_leg, pivots) is True


def test_consolidation_without_pivots():
    prev_leg = _Leg("2024-01-01", "2024-01-05")
    cur_leg = _Leg("2024-02-01", "2024-02-05")
    # 无中枢信息 → 不构成趋势（需≥2中枢），按盘整
    assert _in_consolidation(prev_leg, cur_leg, None) is True
    assert _in_consolidation(prev_leg, cur_leg, []) is True


def _seg(direction: str, t0: str, t1: str, p0: float, p1: float) -> Segment:
    return Segment(direction=direction, strokes=[_dir_stroke(direction, t0, t1, p0, p1)])


def _dir_stroke(direction: str, t0: str, t1: str, p0: float, p1: float,
                volume: float = 1000.0, length: int = 8) -> Stroke:
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"

    def mc(idx, p):
        return MergedCandle(idx=idx, time=t0, open=p, high=p + 1, low=p - 1, close=p,
                            raw_start=idx, raw_end=idx)
    start = Fractal(type=sk, candle=mc(0, p0), left=mc(-1, p0), right=mc(1, p0))
    end = Fractal(type=ek, candle=mc(2, p1), left=mc(1, p1), right=mc(3, p1))
    start.candle.time = t0
    end.candle.time = t1
    return Stroke(direction=direction, start=start, end=end, power_price=round(abs(p1 - p0), 2),
                  power_volume=volume, length=length)


def test_weaker_price_and_volume_is_divergence_with_ratios():
    prev = _dir_stroke("up", "D0", "D2", 10, 30, volume=1000, length=8)   # 价差 20
    cur = _dir_stroke("up", "D5", "D7", 25, 35, volume=600, length=8)     # 价差 10，新高 35>30
    res = check_divergence(cur, prev)
    assert res.is_diverged is True
    assert res.price_ratio == 0.5
    assert res.volume_ratio == 0.6
    assert res.length_ratio == 1.0
    assert res.strength == "strong"          # 0.5 < 0.6


def test_weaker_price_but_stronger_volume_and_length_is_not_divergence():
    """价差更弱但量能、时长都没弱：不满足「量能或时长至少一项更弱」，不算背驰。"""
    prev = _dir_stroke("up", "D0", "D2", 10, 30, volume=1000, length=8)
    cur = _dir_stroke("up", "D5", "D7", 25, 35, volume=1500, length=9)
    res = check_divergence(cur, prev)
    assert res.is_diverged is False
    assert res.price_ratio == 0.5


def test_stronger_price_force_is_not_divergence():
    prev = _dir_stroke("up", "D0", "D2", 10, 20)
    cur = _dir_stroke("up", "D5", "D7", 12, 40, volume=500, length=4)
    assert check_divergence(cur, prev).is_diverged is False


def test_strength_bands_by_price_ratio():
    prev = _dir_stroke("up", "D0", "D2", 0, 100, volume=1000)
    for p1, expected in [(50, "strong"), (70, "medium"), (90, "weak")]:
        cur = _dir_stroke("up", "D5", "D7", 100, 100 + p1, volume=500)
        assert check_divergence(cur, prev).strength == expected


def test_no_divergence_without_new_extreme():
    """价格没有创新高时，即使力度更弱也不比较（逐段检测里直接跳过）。"""
    legs = [
        _dir_stroke("up", "D0", "D2", 10, 30),
        _dir_stroke("down", "D2", "D4", 30, 20),
        _dir_stroke("up", "D4", "D6", 20, 28, volume=100, length=3),  # 28 < 30，未创新高
    ]
    res = find_stroke_divergences(legs)
    assert res[-1].is_diverged is False


def test_segment_divergence_uses_segment_force():
    segs = [
        _seg("up", "D0", "D2", 10, 30),
        _seg("down", "D2", "D5", 30, 20),
        Segment(direction="up", strokes=[_dir_stroke("up", "D5", "D7", 25, 35, volume=600)]),
    ]
    res = find_segment_divergences(segs)
    assert len(res) == len(segs)
    assert res[-1].is_diverged is True
    # 线段价差取两端分型价（K线高/低点），比值按线段自身力度计算
    assert res[-1].price_ratio == round(segs[2].power_price / segs[0].power_price, 2)


def test_stroke_and_segment_divergence_share_semantics():
    legs = [
        _dir_stroke("up", "D0", "D2", 10, 30),
        _dir_stroke("down", "D2", "D5", 30, 20),
        _dir_stroke("up", "D5", "D7", 25, 35, volume=600),
    ]
    segs = [Segment(direction=s.direction, strokes=[s]) for s in legs]
    a = find_stroke_divergences(legs)
    b = find_segment_divergences(segs)
    assert [x.is_diverged for x in a] == [x.is_diverged for x in b]


def test_description_explains_force_without_macd():
    prev = _dir_stroke("up", "D0", "D2", 10, 30, volume=1000)
    cur = _dir_stroke("up", "D5", "D7", 25, 35, volume=600)
    res = check_divergence(cur, prev)
    assert "价差" in res.description and "量能" in res.description
    assert "MACD" not in res.description
