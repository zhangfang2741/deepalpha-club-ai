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


def find_fractals(merged: list[MergedCandle]) -> list[Fractal]:
    """在合并K线序列上识别全部有效顶底分型，按合并K线索引升序返回。

    只做「局部三根」的顶/底判定，不在分型层做价格贪心合并——旧实现会在同型分型
    之间只保留价格极值那一个，用纯价格丢弃分型，容易在震荡区错位/漏掉真实分型，
    也让上层的「笔」失去正确的候选端点。缠论的顶底交替与最小间隔约束属于「成笔」
    阶段的职责（见 stroke.find_strokes），此处保持分型的完整性。

    注：相邻的一顶一底（M/W 形态，中心仅隔1根）都是合法分型，均予保留，
    是否成笔由笔层的最小间隔规则决定。
    """
    if len(merged) < 3:
        return []

    fractals: list[Fractal] = []
    for i in range(1, len(merged) - 1):
        left, mid, right = merged[i - 1], merged[i], merged[i + 1]
        if _is_top_fractal(left, mid, right):
            fractals.append(Fractal(type="top", candle=mid, left=left, right=right))
        elif _is_bottom_fractal(left, mid, right):
            fractals.append(Fractal(type="bottom", candle=mid, left=left, right=right))

    return fractals
