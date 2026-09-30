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


class Overall(BaseModel):
    grade: str | None
    score: float | None
    universe_percentile: float | None
    dimensions_used: int
    capped: bool
    note: str | None = Field(None, description="封顶 / 分析师不足 / 维度不足的说明")
    text: str | None


class FormulaInput(BaseModel):
    label: str
    value: str
    note: str | None = None


class MetricFormula(BaseModel):
    expression: str
    inputs: list[FormulaInput]


class MetricOut(BaseModel):
    key: str
    name: str
    description: str
    direction: Literal["lower_better", "higher_better"]
    value: float | None
    display_value: str
    status: str
    status_note: str | None
    percentile: float | None
    grade: str | None
    sector_median: float | None
    sector_median_display: str | None
    diff_to_median_pct: float | None
    distribution: dict[str, float] | None
    formula: MetricFormula | None
    position_text: str | None


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
