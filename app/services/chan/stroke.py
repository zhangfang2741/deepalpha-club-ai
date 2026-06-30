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


# 笔成立要求：两分型之间（合并后K线）至少间隔4根，即共5根K线
_MIN_GAP = 4


def find_strokes(fractals: list[Fractal]) -> list[Stroke]:
    """从顶底分型序列识别笔。

    规则：
    1. 相邻分型必须是一顶一底（已由 find_fractals 保证）
    2. 两分型在合并K线序列中的索引差 >= MIN_GAP（至少5根合并K线）
    3. 笔的方向由起点分型类型决定（底→顶=上升笔，顶→底=下降笔）
    """
    strokes: list[Stroke] = []

    for i in range(len(fractals) - 1):
        f1, f2 = fractals[i], fractals[i + 1]

        # 检查K线数量是否足够
        if f2.idx - f1.idx < _MIN_GAP:
            continue

        if f1.type == "bottom" and f2.type == "top":
            # 上升笔还要求终点高点高于起点高点
            if f2.price > f1.price:
                strokes.append(Stroke(direction="up", start=f1, end=f2))
        elif f1.type == "top" and f2.type == "bottom":
            # 下降笔还要求终点低点低于起点低点
            if f2.price < f1.price:
                strokes.append(Stroke(direction="down", start=f1, end=f2))

    return strokes
