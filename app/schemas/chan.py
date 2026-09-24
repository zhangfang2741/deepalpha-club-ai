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
    action_label: str      # 中文技术形态标签（描述技术面强弱，非操作建议）
    bias: str              # bullish / bearish / neutral
    reasons: list[str]     # 依据（为什么）
    caveats: list[str]     # 风险提示


class MarketNarrativeOut(BaseModel):
    """大白话形态解读。"""
    phase: str            # 阶段代码
    phase_label: str      # 阶段中文标签
    headline: str         # 一句话形态概括
    details: list[str]    # 分条解读（趋势 / 位置 / 量价 / 动能）


class PhaseChecklistItemOut(BaseModel):
    label: str
    detail: str
    state: Literal["done", "pending"]


class PhaseBranchOut(BaseModel):
    outcome: Literal["type2", "type3", "back_to_range"]
    condition_label: str
    result_label: str


class StageGuideStepOut(BaseModel):
    key: str
    title: str
    detail: str


class StageGuideOut(BaseModel):
    current_index: int
    steps: list[StageGuideStepOut]
    why_it_matters: str


class PivotPhaseOut(BaseModel):
    """中枢生命周期状态机：当前走到哪一步（见 app/services/chan/pivot_phase.py）。"""
    phase: Literal["pivot_forming", "pivot_oscillating", "leaving", "retrace_confirmed", "divergence_turn"]
    phase_label: str
    direction: Optional[Literal["up", "down"]] = None
    pivot: PivotOut
    checklist: list[PhaseChecklistItemOut]
    reason: str
    confirmed: bool = True
    branches: list[PhaseBranchOut] = []
    stage_guide: StageGuideOut


class StructureLayerOut(BaseModel):
    """结构分层判断依据的一条（见 app/services/chan/structure_layers.py）。"""
    layer: Literal["stroke", "segment", "pivot", "signal"]
    label: str
    title: str
    detail: str


class StructureGapRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    industry_view: str   # 用户对该标的产业结构的判断（主观基本面输入）
    freq: str = "daily"


class GapItemOut(BaseModel):
    dimension: str
    market_says: str
    industry_says: str
    direction: Literal["price_lags_industry", "price_ahead_of_fundamentals", "unclear"]
    interpretation: str


class StructureGapResponse(BaseModel):
    symbol: str
    aligned: list[str]           # 技术面与产业面一致处（多已定价）
    gaps: list[GapItemOut]       # 背离处（重点）
    key_question: str            # 最值得研究的问题
    caveats: list[str]           # 诚实边界


class GapJobStatus(BaseModel):
    """GAP 异步任务状态：提交后返回 pending，轮询取回 done/failed。"""
    job_id: str
    status: Literal["pending", "done", "failed"]
    result: Optional[StructureGapResponse] = None
    error: Optional[str] = None


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
    # 走势类型（基于中枢排布）：up_trend / down_trend / consolidation / none
    walk_type: str = "none"
    walk_type_label: str = ""  # 走势类型人话标签
    # 走势展望（延续 vs 转折）：转折向上/转折向下、延续上涨/延续下跌、
    # 盘整上破/盘整下破、盘整延续、未明（枚举值见 analyzer._compute_trend_outlook）
    trend_outlook: str = "unclear"
    trend_outlook_label: str = ""  # 走势展望人话标签
    summary: str
    recommendation: Optional[RecommendationOut] = None
    narrative: Optional[MarketNarrativeOut] = None  # 大白话形态解读
    pending_notes: list[str] = []  # 最右侧未确认结构的提示
    pivot_phase: Optional[PivotPhaseOut] = None  # 中枢生命周期：走到哪一步
    structure_layers: list[StructureLayerOut] = []  # 按笔/线段/中枢/买卖点分层的判断依据
    structure_headline: Optional[str] = None  # 按线段+笔+中枢位置+买卖点拼的一句摘要


class SubLevelResponse(BaseModel):
    """次级别确认：日线定方向 × 30 分钟找买卖点。"""
    symbol: str
    daily_bias: str               # bullish / bearish / neutral
    daily_bias_label: str         # 日线形态倾向文案（与详情页一致）
    sub_freq: str                 # 次级别周期，目前固定 30min
    verdict: Literal["resonance_buy", "resonance_sell", "counter_trend", "waiting", "unavailable"]
    verdict_label: str
    detail: str
    recent_signals: list[SignalOut] = []  # 30 分钟最近两个交易日内的买卖点
