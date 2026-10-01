"""量化研究响应结构（设计 §5.1）。文案由后端按 lang 生成，同时给原始数值；不含数据来源字段。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AsOf(BaseModel):
    price_date: str | None = Field(None, description="行情收盘日")
    fiscal_period: str | None = Field(None, description="最新财报期，如 FY27 Q2")
    filing_date: str | None = Field(None, description="财报披露日")
    estimates_date: str | None = Field(None, description="一致预期更新日")


class PeerGroup(BaseModel):
    sector_key: str
    sector_name: str
    sample_size: int
    in_universe: bool
    text: str


class CashFlows(BaseModel):
    operating: float
    investing: float
    financing: float


class Stage(BaseModel):
    key: str
    name: str
    unprofitable: bool
    cash_flows: CashFlows
    note: str
    revenue_growth_pct: float | None = None   # 营收同比（%），阶段判定主轴
    revenue_cagr_3y_pct: float | None = None  # 营收 3 年复合增速（%），不足 3 年为空


class Overall(BaseModel):
    grade: str | None = None
    score: float | None
    universe_percentile: float | None = None
    dimensions_used: int
    capped: bool
    note: str | None = Field(None, description="封顶 / 分析师不足 / 维度不足的说明")
    text: str | None


class FormulaInput(BaseModel):
    label: str
    value: str
    note: str | None = None
    hint: str | None = None  # 大白话：这个输入是什么、取的哪个期间


class MetricFormula(BaseModel):
    expression: str
    inputs: list[FormulaInput]


class MetricInterpretation(BaseModel):
    """指标定义、投资含义、适用边界与不依赖数据的通用公式。"""
    what: str            # 指标含义
    role: str = ""       # 在维度里的作用
    threshold: str = ""  # 适用边界
    calculation: str | None = None  # 通用公式，与真实数字代入分开
    full_name: str = ""  # 全称（如「净资产收益率 ROE（Return on Equity）」）
    plain: str = ""      # 大白话释义（带例子，不讲口径）
    reading: str = ""    # 高 / 低怎么看
    why: str = ""        # 为什么重要
    purpose: str = ""    # 我们为什么用它（在评级里的作用）


class MetricOut(BaseModel):
    key: str
    name: str
    description: str
    direction: Literal["lower_better", "higher_better"]
    value: float | None = None
    display_value: str
    status: str
    status_note: str | None = None
    percentile: float | None
    grade: str | None
    sector_median: float | None = None
    sector_median_display: str | None = None
    diff_to_median_pct: float | None = None
    distribution: dict[str, float] | None = None
    formula: MetricFormula | None = None
    position_text: str | None = None
    interpretation: MetricInterpretation | None = None


class MetricGroup(BaseModel):
    name: str
    metrics: list[MetricOut]


class KeyFact(BaseModel):
    metric: str
    text: str


class Dimension(BaseModel):
    key: str
    name: str
    description: str
    grade: str | None
    score: float | None
    status: Literal["ok", "unavailable", "accumulating"]
    status_note: str | None
    is_highest: bool
    is_lowest: bool
    key_fact: KeyFact | None
    formula: str | None
    groups: list[MetricGroup]
    counts_in_overall: bool = True  # False = 只展示、不计入综合等级（护城河）


class MoatYear(BaseModel):
    year: int
    value: float          # 当年 ROIC（金融股为 ROE）


class MoatEvidenceOut(BaseModel):
    """财务证据：多年回报率 vs 资金成本。"""
    metric: Literal["roic", "roe"]
    metric_name: str
    years: list[MoatYear]          # 新 → 旧
    cost_of_capital: float
    years_above: int
    n_years: int
    avg_spread: float | None
    level: Literal["strong", "moderate", "weak"]
    level_name: str
    text: str                      # 一句话结论


class MoatSourceOut(BaseModel):
    key: str
    name: str
    strength: Literal["none", "weak", "moderate", "strong"]
    strength_name: str
    reason: str
    quotes: list[str]              # 年报英文原文，逐字核对过


class MoatOut(BaseModel):
    """护城河（Morningstar 框架：宽 / 窄 / 无 + 趋势）。只展示，不计入综合等级。"""
    status: Literal["ok", "pending", "not_covered"]
    status_note: str | None = None
    rating: Literal["wide", "narrow", "none"] | None = None
    rating_name: str | None = None
    trend: Literal["widening", "stable", "narrowing"] | None = None
    trend_name: str | None = None
    summary: str | None = None
    evidence: MoatEvidenceOut | None = None
    sources: list[MoatSourceOut] = []
    threats: str | None = None
    filed_date: str | None = None
    tenk_url: str | None = None
    method_note: str


class QuantResearchOut(BaseModel):
    market: str
    symbol: str
    name: str | None
    status: Literal["ok", "unsupported_market", "insufficient_data"]
    status_note: str | None = None
    methodology_version: str
    as_of: AsOf | None = None
    peer_group: PeerGroup | None = None
    stage: Stage | None = None
    overall: Overall | None = None
    dimensions: list[Dimension] = []
    moat: MoatOut | None = None
    disclaimer: str


class GradeBand(BaseModel):
    grade: str
    min_percentile: float


class MethodologyMetric(BaseModel):
    key: str
    name: str
    group: str
    direction: str
    description: str


class MethodologyDimension(BaseModel):
    key: str
    name: str
    description: str
    metrics: list[MethodologyMetric]


class MethodologyOut(BaseModel):
    methodology_version: str
    sections: list[dict[str, str]] = Field(description="[{title, body}] 按顺序展示的说明段落")
    grade_bands: list[GradeBand]
    dimensions: list[MethodologyDimension]
    disclaimer: str
