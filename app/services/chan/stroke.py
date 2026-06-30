"""缠论笔识别：顶底分型之间至少5根K线（独立K线原则）"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.chan.fractal import Fractal


@dataclass
class Stroke:
    """笔：相邻顶底分型之间的价格走势"""
    direction: Literal["up", "down"]  # up=上升笔，down=下降笔
    start: Fractal
    end: Fractal

    @property
    def start_time(self) -> str:
        return self.start.time

    @property
    def end_time(self) -> str:
        return self.end.time

    @property
    def start_price(self) -> float:
        return self.start.price

    @property
    def end_price(self) -> float:
        return self.end.price

    @property
    def high(self) -> float:
        return max(self.start_price, self.end_price)

    @property
    def low(self) -> float:
        return min(self.start_price, self.end_price)

    @property
    def amplitude(self) -> float:
        return abs(self.end_price - self.start_price)

    @property
    def start_idx(self) -> int:
        return self.start.idx

    @property
    def end_idx(self) -> int:
        return self.end.idx


# 笔成立要求：两分型之间（合并后K线）至少间隔4根，即共5根K线（缠论“新笔”标准）
_MIN_GAP = 4


def find_strokes(fractals: list[Fractal], min_gap: int = _MIN_GAP) -> list[Stroke]:
    """从顶底分型序列识别笔。

    规则：
    1. 成笔的两端必须一顶一底，方向由起点决定（底→顶=上升笔，顶→底=下降笔）
    2. 两分型在合并K线序列中的索引差 >= min_gap（至少 min_gap+1 根合并K线）
    3. 用游标 last 记录待成笔的起点：遇到同型分型保留更极端者（更高的顶 / 更低的底），
       遇到间隔不足的异型分型则忽略——避免简单递增在分型密集时丢弃分型、导致笔偏少且错位

    min_gap 可调：高级别（如周线）可适当减小以识别更多笔，日线保持默认 4。
    """
    if len(fractals) < 2:
        return []

    strokes: list[Stroke] = []
    last = fractals[0]

    for k in range(1, len(fractals)):
        f = fractals[k]

        if f.type == last.type:
            # 同型分型：保留更极端的一端作为新的待成笔起点
            if (last.type == "top" and f.price > last.price) or (
                last.type == "bottom" and f.price < last.price
            ):
                last = f
            continue

        # 异型分型：间隔不足则忽略当前分型，保留 last 等待后续更远的分型
        if f.idx - last.idx < min_gap:
            continue

        if last.type == "bottom" and f.price > last.price:
            strokes.append(Stroke(direction="up", start=last, end=f))
            last = f
        elif last.type == "top" and f.price < last.price:
            strokes.append(Stroke(direction="down", start=last, end=f))
            last = f
        # 价格方向不符（罕见，数据异常）：忽略 f，保留 last

    return strokes
