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
    # 形态是否已锁定：右侧K线不是最后一根合并K线时才成立
    # （否则后续K线的包含处理仍可能改变右侧K线，进而使分型失效或移动）
    confirmed: bool = True

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

        # 确定合并方向：看倒数第二根与倒数第一根的关系（去包含后高低同向，比高点即可）
        if len(merged) >= 2:
            direction_up = merged[-2].high < prev.high  # 上升趋势
        else:
            # 只有一根在手时无前序趋势可参照，用当前K线是否上破 prev 高点近似定向，
            # 避免一律默认「上升」在开局下跌时把首根合并K线的低点取错
            direction_up = mc.high > prev.high

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


def _raw_fractals(merged: list[MergedCandle]) -> list[Fractal]:
    """在合并K线序列上做「局部三根」的顶/底判定，返回全部原始分型（按索引升序）。"""
    fractals: list[Fractal] = []
    for i in range(1, len(merged) - 1):
        left, mid, right = merged[i - 1], merged[i], merged[i + 1]
        if _is_top_fractal(left, mid, right):
            fractals.append(Fractal(type="top", candle=mid, left=left, right=right))
        elif _is_bottom_fractal(left, mid, right):
            fractals.append(Fractal(type="bottom", candle=mid, left=left, right=right))
    return fractals


def _confirm_fractals(raw: list[Fractal], min_spacing: int) -> list[Fractal]:
    """把原始分型序列处理成「有效分型」序列（缠论的分型确认）。

    两条规则同时施加：
    1. 顶底交替：连续同型分型只保留极值一端（更高的顶 / 更低的底）。
    2. 最小间隔：相邻保留分型的中心K线之间至少间隔 min_spacing 根独立K线
       （即索引差 >= min_spacing + 1）。间隔不足的相邻一顶一底属于共用K线的
       重叠 M/W 噪声，按极值取舍、不予并列保留——否则在横盘 / 涨跌停一字板
       这类几乎每根合并K线都是局部极值的行情里，会画出成片重叠分型。

    被过滤掉的都是间隔 < min_spacing+1 的分型，其两端间隔远小于成笔所需的
    min_gap（默认4），本就不可能成笔，故笔 / 线段结果不受影响，只让图更干净。
    """
    if not raw:
        return []

    threshold = min_spacing + 1
    out: list[Fractal] = []
    last = raw[0]
    for f in raw[1:]:
        if f.type == last.type:
            # 同型：仅保留更极端者；若它已在输出末尾，一并替换
            more_extreme = (last.type == "top" and f.price > last.price) or (
                last.type == "bottom" and f.price < last.price
            )
            if more_extreme:
                if out and out[-1] is last:
                    out[-1] = f
                last = f
            continue
        # 异型：间隔达标才确认为一个新的有效分型；否则视为重叠噪声丢弃
        if f.idx - last.idx >= threshold:
            if not out or out[-1] is not last:
                out.append(last)
            out.append(f)
            last = f

    return out


def find_fractals(merged: list[MergedCandle], min_spacing: int = 1) -> list[Fractal]:
    """在合并K线序列上识别有效顶底分型，按合并K线索引升序返回。

    先做「局部三根」的原始分型判定，再做分型确认（见 _confirm_fractals）：
    保证顶底交替，且相邻分型间至少间隔 min_spacing 根独立K线。

    min_spacing 默认 1（缠论「两分型间至少1根独立K线」）。传 0 可关闭间隔过滤、
    返回全部原始分型（仍保持顶底交替时取极值）。注意：这里只过滤间隔不足、本就
    无法成笔的重叠噪声，不改变笔 / 线段结果——只让图上分型不再密集。
    """
    if len(merged) < 3:
        return []
    return _confirm_fractals(_raw_fractals(merged), max(0, min_spacing))
