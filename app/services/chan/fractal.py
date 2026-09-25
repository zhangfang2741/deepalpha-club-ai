"""缠论分型数据结构：合并K线 + 顶底分型。

包含关系处理与分型识别已切换到 czsc 引擎（见 czsc_adapter.py），本模块只保留
对外 dataclass 定义，供 adapter 转换结果与下游自研代码（线段/背驰/买卖点等）消费。
"""
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
    volume: float = 0.0  # 所含原始K线成交量之和
    # 所含最后一根原始K线的时间，仅供展示。time 是 czsc 按合并方向选定的那根（笔/分型按它对位，
    # 不能改）；今天被昨天包含时 time 仍是昨天，图上要显示 end_time 才看得出今天的数据已在里面。
    end_time: str = ""


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

