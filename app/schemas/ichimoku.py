"""一目均衡表分析请求/响应 Schema"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class CandleOut(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float


class LinePointOut(BaseModel):
    time: str
    value: float


class IchimokuSignalOut(BaseModel):
    type: Literal["tk_golden", "tk_dead", "kumo_up", "kumo_down"]
    label: str
    time: str
    price: float
    strength: Literal["strong", "medium", "weak"]
    is_buy: bool
    description: str


class IchimokuStateOut(BaseModel):
    price: float
    price_vs_cloud: Literal["above", "in", "below", "na"]
    cloud_color: Literal["bullish", "bearish", "na"]
    tk_relation: Literal["tenkan_above", "tenkan_below", "aligned", "na"]
    chikou_relation: Literal["above", "below", "aligned", "na"]
    tenkan: Optional[float] = None
    kijun: Optional[float] = None
    cloud_top: Optional[float] = None
    cloud_bottom: Optional[float] = None


class RecommendationOut(BaseModel):
    action: str
    action_label: str
    bias: str
    reasons: list[str]
    caveats: list[str]


class IchimokuAnalysisResponse(BaseModel):
    symbol: str
    bars_count: int
    conversion_period: int
    base_period: int
    span_b_period: int
    displacement: int
    candles: list[CandleOut]
    tenkan: list[LinePointOut]
    kijun: list[LinePointOut]
    senkou_a: list[LinePointOut]
    senkou_b: list[LinePointOut]
    chikou: list[LinePointOut]
    signals: list[IchimokuSignalOut]
    state: Optional[IchimokuStateOut] = None
    summary: str
    recommendation: Optional[RecommendationOut] = None
