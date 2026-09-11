"""缠论背驰趋势/盘整分类测试。

不变量：两个被比较的同向段之间夹着一个完整中枢 → 趋势背驰；否则盘整背驰。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.chan.divergence import MACDData, check_divergence, _in_consolidation
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.stroke import Stroke


@dataclass
class _Leg:
    start_time: str
    end_time: str


@dataclass
class _Pivot:
    start_time: str
    end_time: str


def test_trend_when_pivot_between_legs():
    prev_leg = _Leg("2024-01-01", "2024-01-05")
    cur_leg = _Leg("2024-02-01", "2024-02-05")
    # 中枢完整地夹在两段之间 → 趋势背驰（非盘整）
    pivots = [_Pivot("2024-01-10", "2024-01-25")]
    assert _in_consolidation(prev_leg, cur_leg, pivots) is False


def test_consolidation_when_pivot_not_between():
    prev_leg = _Leg("2024-01-01", "2024-01-05")
    cur_leg = _Leg("2024-01-06", "2024-01-10")
    # 中枢跨越/包住两段，而非夹在中间 → 盘整背驰
    pivots = [_Pivot("2024-01-01", "2024-01-10")]
    assert _in_consolidation(prev_leg, cur_leg, pivots) is True


def test_default_trend_without_pivots():
    prev_leg = _Leg("2024-01-01", "2024-01-05")
    cur_leg = _Leg("2024-02-01", "2024-02-05")
    # 无中枢信息时保守按趋势（不判盘整）
    assert _in_consolidation(prev_leg, cur_leg, None) is False
    assert _in_consolidation(prev_leg, cur_leg, []) is False


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
