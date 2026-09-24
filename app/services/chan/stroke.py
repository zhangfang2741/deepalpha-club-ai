"""缠论笔数据结构。

笔识别已切换到 czsc 引擎（见 czsc_adapter.py），本模块只保留对外 dataclass
定义，供 adapter 转换结果与下游自研代码（线段/背驰/买卖点等）消费。
"""
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
    # 笔是否已确认：最后一笔的端点可能被后续K线突破/延伸，转折点尚未被反向结构确认
    confirmed: bool = True
    # 力度（取自 czsc 的笔）：价差 = 两端分型价差（两位小数）；量能 = 笔内去掉首尾两根的
    # 成交量合计；时长 = 笔包含的去包含K线根数。背驰与一类买卖点都按这三项比较力度。
    power_price: float = 0.0
    power_volume: float = 0.0
    length: int = 0

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
