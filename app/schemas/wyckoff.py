"""威科夫方法论分析请求/响应 Schema。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class TradingRangeOut(BaseModel):
    kind: Literal["accumulation", "distribution"]
    support: float
    resistance: float
    start_time: str
    end_time: str


class WyckoffEventOut(BaseModel):
    code: str          # SC / AR / ST / SPRING / SOS / UT / UTAD / SOW / LPS / LPSY / PS / PSY / BC / TEST / BU
    name: str          # 中文名
    time: str
    price: float
    volume_ratio: float
    phase: str         # A / B / C / D / E
    description: str


class LawOut(BaseModel):
    key: Literal["supply_demand", "cause_effect", "effort_result"]
    name: str
    verdict: str
    detail: str


class PhaseOut(BaseModel):
    stage: str         # accumulation / markup / distribution / markdown / undetermined
    stage_label: str
    phase: str         # A–E
    phase_label: str
    breakout: Literal["up", "down", "none"]


class RecommendationOut(BaseModel):
    action: str        # accumulate / buy / hold / reduce / avoid / watch
    action_label: str
    bias: Literal["bullish", "bearish", "neutral"]
    reasons: list[str]
    caveats: list[str]


class CandleOut(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class WyckoffAnalysisResponse(BaseModel):
    symbol: str
    bars_count: int
    context: str
    candles: list[CandleOut]
    trading_range: Optional[TradingRangeOut]
    events: list[WyckoffEventOut]
    phase: Optional[PhaseOut]
    laws: list[LawOut]
    stage_label: str
    position_desc: str
    summary: str
    recommendation: Optional[RecommendationOut] = None
