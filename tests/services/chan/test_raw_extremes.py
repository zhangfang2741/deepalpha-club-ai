"""合并 K 线所含原始 K 线的真实最高 / 最低价（SMC / 威科夫打开时画影线用）。"""
from __future__ import annotations

from app.services.chan.fractal import MergedCandle
from app.services.chan.raw_extremes import raw_extremes


def _bar(t: str, h: float, l: float) -> dict:
    return {"time": t, "open": (h + l) / 2, "high": h, "low": l, "close": (h + l) / 2, "volume": 1.0}


def _mc(idx: int, start: int, end: int, h: float, l: float) -> MergedCandle:
    return MergedCandle(idx=idx, time="t", open=l, high=h, low=l, close=h, raw_start=start, raw_end=end)


def test_union_of_raw_bars_in_each_group():
    bars = [_bar("d1", 10, 8), _bar("d2", 12, 9), _bar("d3", 11, 10), _bar("d4", 15, 13)]
    # 前三根并成一根（上行合并：高取最大、低取最大 → 缠论的 high=12, low=10），第四根单独
    mcs = [_mc(0, 0, 2, 12, 10), _mc(1, 3, 3, 15, 13)]
    assert raw_extremes(bars, mcs) == [(12, 8), (15, 13)]      # 影线用原始最低 8，而不是合并后的 10


def test_downward_merge_keeps_raw_high():
    bars = [_bar("d1", 20, 15), _bar("d2", 18, 12)]
    mcs = [_mc(0, 0, 1, 18, 12)]                                # 下行合并：高取最小 → 18，原始最高是 20
    assert raw_extremes(bars, mcs) == [(20, 12)]


def test_never_narrower_than_merged_candle():
    bars = [_bar("d1", 10, 9), _bar("d2", 11, 10)]
    assert raw_extremes(bars, [_mc(0, 0, 1, 12, 8)]) == [(12, 8)]


def test_leading_bars_before_first_candle_are_not_counted():
    # czsc 会丢掉首笔确认前的前导 K 线：它们不属于任何合并 K 线，不能算进第一根
    bars = [_bar("d0", 99, 1), _bar("d1", 10, 9), _bar("d2", 11, 10)]
    assert raw_extremes(bars, [_mc(0, 1, 2, 11, 10)]) == [(11, 9)]


def test_out_of_range_indices_fall_back_to_merged_values():
    bars = [_bar("d1", 10, 9)]
    assert raw_extremes(bars, [_mc(0, 5, 7, 12, 8)]) == [(12, 8)]
    assert raw_extremes([], [_mc(0, 0, 1, 12, 8)]) == [(12, 8)]
