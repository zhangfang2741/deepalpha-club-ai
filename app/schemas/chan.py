"""缠论分析请求/响应 Schema"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChanAnalysisRequest(BaseModel):
    symbol: str = Field(description="股票代码，如 AAPL 或 SH000001")
    start_date: str = Field(description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(description="结束日期，格式 YYYY-MM-DD")
    freq: str = Field(default="daily", description="K线周期：daily / weekly")


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


class StrokeOut(BaseModel):
    direction: Literal["up", "down"]
    start_time: str
    end_time: str
    start_price: float
    end_price: float
    high: float
    low: float


class SegmentOut(BaseModel):
    direction: Literal["up", "down"]
    start_time: str
    end_time: str
    start_price: float
    end_price: float
    high: float
    low: float
    stroke_count: int


class PivotOut(BaseModel):
    zg: float       # 中枢高点
    zd: float       # 中枢低点
    gg: float       # 区间最高点
    dd: float       # 区间最低点
    start_time: str
    end_time: str
    level: Literal["stroke", "segment"]


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
