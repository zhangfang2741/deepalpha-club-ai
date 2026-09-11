"""缠论背驰趋势/盘整分类测试。

不变量：两个被比较的同向段之间夹着一个完整中枢 → 趋势背驰；否则盘整背驰。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.chan.divergence import _in_consolidation


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
