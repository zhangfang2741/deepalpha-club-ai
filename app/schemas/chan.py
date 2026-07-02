"""缠论分析请求/响应 Schema"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class MergedCandleOut(BaseModel):
    idx: int
    time: str
    high: float
    low: float
    open: float
    close: float


class FractalOut(BaseModel):
    type: Literal["top", "bottom"]
    time: str
    price: float
    idx: int
    confirmed: bool = True  # 形态是否已被后续K线锁定


class StrokeOut(BaseModel):
    direction: Literal["up", "down"]
    start_time: str
    end_time: str
    start_price: float
    end_price: float
    high: float
    low: float
    confirmed: bool = True  # 是否已完成确认（最后一笔为 False）


class SegmentOut(BaseModel):
    direction: Literal["up", "down"]
    start_time: str
    end_time: str
    start_price: float
    end_price: float
    high: float
    low: float
    stroke_count: int
    confirmed: bool = True  # 是否已确认结束（最后一条为 False）


class PivotOut(BaseModel):
    zg: float       # 中枢高点
    zd: float       # 中枢低点
    gg: float       # 区间最高点
    dd: float       # 区间最低点
    start_time: str
    end_time: str
    level: Literal["stroke", "segment"]
    confirmed: bool = True  # 是否已确认（最后一个可能仍在延伸）


class MACDOut(BaseModel):
    times: list[str]
    dif: list[float]
    dea: list[float]
    bar: list[float]


class SignalOut(BaseModel):
    type: Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]
    label: str
    time: str
    price: float
    strength: Literal["strong", "medium", "weak"]
    is_buy: bool
    description: str
    area_ratio: Optional[float] = None
    confirmed: bool = True  # 是否已确认（落在未确认笔上的信号为 False）


class RecommendationOut(BaseModel):
    action: str            # buy / sell / hold_bullish / hold_bearish / watch
    action_label: str      # 中文操作标签
    bias: str              # bullish / bearish / neutral
    reasons: list[str]     # 依据（为什么）
    caveats: list[str]     # 风险提示


class ChanAnalysisResponse(BaseModel):
    symbol: str
    bars_count: int
    merged_candles: list[MergedCandleOut]
    fractals: list[FractalOut]
    strokes: list[StrokeOut]
    segments: list[SegmentOut]
    stroke_pivots: list[PivotOut]
    segment_pivots: list[PivotOut]
    macd: Optional[MACDOut]
    signals: list[SignalOut]
    current_trend: str
    summary: str
    recommendation: Optional[RecommendationOut] = None
    pending_notes: list[str] = []  # 最右侧未确认结构的提示
