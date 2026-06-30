"""缠论分型识别：包含关系处理 + 顶底分型"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class MergedCandle:
    """经包含关系处理后的合并K线"""
    idx: int
    time: str
    open: float
    high: float
    low: float
    close: float
    raw_start: int  # 原始K线起始索引
    raw_end: int    # 原始K线结束索引


@dataclass
class Fractal:
    """顶底分型"""
    type: Literal["top", "bottom"]
    candle: MergedCandle
    left: MergedCandle
    right: MergedCandle

    @property
    def time(self) -> str:
        return self.candle.time

    @property
    def price(self) -> float:
        return self.candle.high if self.type == "top" else self.candle.low

    @property
    def idx(self) -> int:
        return self.candle.idx


def merge_candles(bars: list[dict]) -> list[MergedCandle]:
    """处理K线包含关系，返回合并后的独立K线序列。

    包含关系：若K线A的high >= K线B的high 且 A的low <= K线B的low（或反之），
    则A包含B（或B包含A）。合并方向：上升取高高，下降取低低。
    """
    if not bars:
        return []

    merged: list[MergedCandle] = []
    for i, bar in enumerate(bars):
        mc = MergedCandle(
            idx=i,
            time=bar["time"],
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            raw_start=i,
            raw_end=i,
        )
        if not merged:
            merged.append(mc)
            continue

        prev = merged[-1]
        # 判断包含关系
        prev_contains_cur = prev.high >= mc.high and prev.low <= mc.low
        cur_contains_prev = mc.high >= prev.high and mc.low <= prev.low

        if not (prev_contains_cur or cur_contains_prev):
            mc.idx = len(merged)
            merged.append(mc)
            continue

        # 确定合并方向：看倒数第二根与倒数第一根的关系
        if len(merged) >= 2:
            direction_up = merged[-2].high < prev.high  # 上升趋势
        else:
            direction_up = True  # 默认上升

        if direction_up:
            # 上升：取高高、高低
            new_high = max(prev.high, mc.high)
            new_low = max(prev.low, mc.low)
        else:
            # 下降：取低低、低高
            new_high = min(prev.high, mc.high)
            new_low = min(prev.low, mc.low)

        prev.high = new_high
        prev.low = new_low
        prev.raw_end = i
        # 用包含后的K线时间取终点
        if direction_up:
            prev.time = mc.time if mc.high == new_high else prev.time
        else:
            prev.time = mc.time if mc.low == new_low else prev.time

    # 重新编号
    for i, mc in enumerate(merged):
        mc.idx = i

    return merged


def _is_top_fractal(left: MergedCandle, mid: MergedCandle, right: MergedCandle) -> bool:
    return mid.high > left.high and mid.high > right.high and mid.low > left.low and mid.low > right.low


def _is_bottom_fractal(left: MergedCandle, mid: MergedCandle, right: MergedCandle) -> bool:
    return mid.low < left.low and mid.low < right.low and mid.high < left.high and mid.high < right.high


def find_fractals(merged: list[MergedCandle]) -> list[Fractal]:
    """在合并K线序列上识别顶底分型，并保证顶底严格交替。
    """
    if len(merged) < 3:
        return []

    raw_fractals: list[Fractal] = []
    for i in range(1, len(merged) - 1):
        left, mid, right = merged[i - 1], merged[i], merged[i + 1]
        if _is_top_fractal(left, mid, right):
            raw_fractals.append(Fractal(type="top", candle=mid, left=left, right=right))
        elif _is_bottom_fractal(left, mid, right):
            raw_fractals.append(Fractal(type="bottom", candle=mid, left=left, right=right))

    # 保证顶底交替：同向分型取极值那个
    alternated: list[Fractal] = []
    for f in raw_fractals:
        if not alternated:
            alternated.append(f)
            continue
        prev = alternated[-1]
        if f.type == prev.type:
            # 同向，保留极值更强的
            if f.type == "top" and f.price >= prev.price:
                alternated[-1] = f
            elif f.type == "bottom" and f.price <= prev.price:
                alternated[-1] = f
        else:
            alternated.append(f)

    return alternated
