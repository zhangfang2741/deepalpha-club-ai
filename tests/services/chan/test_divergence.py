"""缠论背驰趋势/盘整分类测试。

不变量：两个被比较的同向段之间夹着一个完整中枢 → 趋势背驰；否则盘整背驰。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.chan.divergence import (
    MACDData,
    check_divergence,
    find_segment_divergences,
    find_stroke_divergences,
    _in_consolidation,
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


def _up_stroke(t0: str, t1: str, p0: float, p1: float) -> Stroke:
    def mc(idx, hi, lo):
        return MergedCandle(idx=idx, time=t0, open=(hi + lo) / 2, high=hi, low=lo,
                            close=(hi + lo) / 2, raw_start=idx, raw_end=idx)
    start = Fractal(type="bottom", candle=mc(0, p0 + 1, p0), left=mc(-1, p0, p0 - 1),
                    right=mc(1, p0, p0 - 1))
    end = Fractal(type="top", candle=mc(2, p1, p1 - 1), left=mc(1, p1 - 1, p1 - 2),
                  right=mc(3, p1 - 1, p1 - 2))
    start.candle.time = t0
    end.candle.time = t1
    return Stroke(direction="up", start=start, end=end)


def test_dif_new_high_rejects_false_divergence():
    # 两段上升笔：当前段 MACD 面积更小（比值<1）但 DIF 峰值更高（黄白线创新高）
    # → 动能其实更强，应判定为「非真背驰」。
    times = ["D0", "D1", "D2", "D3", "D4", "D5"]
    # 前段 D0-D2：面积大(柱 3+3)，DIF 峰值 1.0
    # 后段 D3-D5：面积小(柱 1+1)，DIF 峰值 2.0（创新高）
    macd = MACDData(
        times=times,
        dif=[1.0, 1.0, 1.0, 2.0, 2.0, 2.0],
        dea=[0.0] * 6,
        bar=[3.0, 3.0, 0.0, 1.0, 1.0, 0.0],
    )
    compare = _up_stroke("D0", "D2", 10, 20)
    current = _up_stroke("D3", "D5", 20, 30)  # 价格创新高
    res = check_divergence(current, compare, macd)
    assert res.is_diverged is False
    assert res.dif_ratio > 1.0  # 黄白线创新高


def test_dif_lower_confirms_divergence():
    # 面积更小且 DIF 峰值也更低 → 真背驰
    times = ["D0", "D1", "D2", "D3", "D4", "D5"]
    macd = MACDData(
        times=times,
        dif=[2.0, 2.0, 2.0, 1.0, 1.0, 1.0],  # 后段 DIF 峰值更低
        dea=[0.0] * 6,
        bar=[3.0, 3.0, 0.0, 1.0, 1.0, 0.0],  # 后段面积更小
    )
    compare = _up_stroke("D0", "D2", 10, 20)
    current = _up_stroke("D3", "D5", 20, 30)
    res = check_divergence(current, compare, macd)
    assert res.is_diverged is True
    assert res.area_ratio < 1.0
    assert res.dif_ratio < 1.0


def _seg(direction: str, t0: str, t1: str, p0: float, p1: float) -> Segment:
    return Segment(direction=direction, strokes=[_dir_stroke(direction, t0, t1, p0, p1)])


def _dir_stroke(direction: str, t0: str, t1: str, p0: float, p1: float) -> Stroke:
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"

    def mc(idx, p):
        return MergedCandle(idx=idx, time=t0, open=p, high=p + 1, low=p - 1, close=p,
                            raw_start=idx, raw_end=idx)
    start = Fractal(type=sk, candle=mc(0, p0), left=mc(-1, p0), right=mc(1, p0))
    end = Fractal(type=ek, candle=mc(2, p1), left=mc(1, p1), right=mc(3, p1))
    start.candle.time = t0
    end.candle.time = t1
    return Stroke(direction=direction, start=start, end=end)


def test_segment_divergence_reuses_core_on_segments():
    # 两条同向（上升）线段：后段价格创新高但 MACD 面积更小、DIF 更低 → 线段级背驰
    times = [f"D{i}" for i in range(8)]
    macd = MACDData(
        times=times,
        dif=[2, 2, 2, 0, 0, 1, 1, 1],
        dea=[0] * 8,
        bar=[4, 4, 0, 0, 0, 1, 1, 0],
    )
    segs = [
        _seg("up", "D0", "D2", 10, 20),
        _seg("down", "D2", "D5", 20, 15),
        _seg("up", "D5", "D7", 15, 25),  # 价格创新高
    ]
    res = find_segment_divergences(segs, macd)
    assert len(res) == len(segs)
    # 最后一条上升线段应判定为背驰（面积与 DIF 均衰减）
    assert res[-1].is_diverged is True
    assert res[-1].area_ratio < 1.0


def test_stroke_and_segment_divergence_share_semantics():
    # 同一组段，作为「笔」和「线段」调用应得到一致结果（核心复用）
    times = [f"D{i}" for i in range(8)]
    macd = MACDData(times=times, dif=[2, 2, 2, 0, 0, 1, 1, 1], dea=[0] * 8,
                    bar=[4, 4, 0, 0, 0, 1, 1, 0])
    legs = [
        _dir_stroke("up", "D0", "D2", 10, 20),
        _dir_stroke("down", "D2", "D5", 20, 15),
        _dir_stroke("up", "D5", "D7", 15, 25),
    ]
    segs = [Segment(direction=s.direction, strokes=[s]) for s in legs]
    a = find_stroke_divergences(legs, macd)
    b = find_segment_divergences(segs, macd)
    assert [x.is_diverged for x in a] == [x.is_diverged for x in b]
