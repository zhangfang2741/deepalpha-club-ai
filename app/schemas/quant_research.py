"""量化研究响应结构（设计 §5.1）。文案由后端按 lang 生成，同时给原始数值；不含数据来源字段。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AsOf(BaseModel):
    price_date: str | None = Field(None, description="行情收盘日")
    fiscal_period: str | None = Field(None, description="最新财报期，如 FY27 Q2")
    filing_date: str | None = Field(None, description="财报披露日")
    estimates_date: str | None = Field(None, description="一致预期更新日")
    currency_note: str | None = Field(default=None, description="金额币种说明（港股报表与预期折成港元时给出汇率）")


class PeerGroup(BaseModel):
    sector_key: str
    sector_name: str
    sample_size: int
    in_universe: bool
    text: str
    universe_name: str | None = None  # 比较样本的叫法：标普1500 / A 股市值前 1800 / 港股通及大中型港股


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
    weight: float = 1.0  # 在维度分里的权重（口径相近的利润 / 回报指标合并计权，其余为 1）


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
    weight_pct: int | None = None   # 这一维在综合分里的实际占比（%，按公司阶段加权、只在可用维度间归一）


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


class TrendFacts(BaseModel):
    """基本面动向事实（批量时算好）：预期修正与最近一季的质地变化。不是评分、不进综合等级。"""
    n_analysts: int = 0
    eps_rev_7d: float | None = None    # 本财年 EPS 一致预期近 7 天变化率（小数）
    eps_rev_30d: float | None = None
    eps_rev_90d: float | None = None
    quality_period: str | None = None       # 最近一季的季度截止日
    quality_prev_period: str | None = None  # 对比的上一季
    filing_date: str | None = None          # 最近一季的披露日
    d_rev_yoy_pp: float | None = None       # 营收同比变化（百分点）
    d_gross_m_pp: float | None = None       # 毛利率变化（百分点）
    d_ebit_m_pp: float | None = None        # 经营利润率变化（百分点）
    d_fcf_m_pp: float | None = None         # 自由现金流利润率变化（百分点）


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
    trend: TrendFacts | None = None  # 基本面动向事实（动向雷达用）；旧结果没有
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


class LatestReportOut(BaseModel):
    """最新一份定期财报（年报 / 中报 / 季报）的原文文件。美股是 SEC 网页文档，A 股 / 港股是 PDF。"""

    status: Literal["ok", "unavailable", "unsupported_market"]
    symbol: str
    title: str | None = None
    report_type: str | None = Field(None, description="年报 / 中报 / 季报 / 业绩公告（按 lang 给文案）")
    period: str | None = Field(None, description="报告期末（美股有）")
    filed_date: str | None = Field(None, description="披露日")
    url: str | None = None
    file_type: Literal["pdf", "html"] | None = None


class ReportKeyNumber(BaseModel):
    label: str = Field(description="指标名，如 营收 / 净利润 / 每股收益")
    value: str = Field(description="数值（带币种与单位，保留原文口径）")
    change: str | None = Field(default=None, description="同比 / 环比变化，原文有才写")


class ReportSummary(BaseModel):
    """财报节选的结构化中文要点（大模型整理，只依据原文）。"""

    headline: str = Field(description="一句话概括这期业绩，40 字以内")
    key_numbers: list[ReportKeyNumber] = Field(default_factory=list, description="关键数字，最多 6 条，原文有才写")
    highlights: list[str] = Field(default_factory=list, description="这期发生了什么，4~6 条")
    watch_points: list[str] = Field(default_factory=list, description="原文提到的风险、不确定性或需要留意的变化，2~4 条")
    outlook: str = Field(default="", description="管理层对后续的表述（用「管理层表示…」转述），没有就留空")


class ReportSummaryOut(BaseModel):
    """最新财报的中文要点：生成需要一会儿，status=generating 时客户端过几秒再请求。"""

    status: Literal["ready", "generating", "unavailable", "limit_reached", "disabled", "not_generated", "unreadable"]
    symbol: str
    report_type: str | None = None
    filed_date: str | None = None
    summary: ReportSummary | None = None
    note: str | None = Field(default=None, description="免责说明 / 失败原因")


class StageRankingItem(BaseModel):
    rank: int
    symbol: str
    name: str | None = None
    grade: str | None = None
    score: float
    sector_name: str | None = None
    is_self: bool = False


class StageRankingSelf(BaseModel):
    rank: int
    total: int
    in_universe: bool  # false = 本股不在样本内，名次按它自己的综合分估算


class StageRankingOut(BaseModel):
    """同阶段综合分排名（点企业阶段时展示）：只陈列本模型结果。"""
    market: str
    stage: str
    as_of: str | None = None
    cohort_size: int
    items: list[StageRankingItem]
    self_item: StageRankingSelf | None = None


class RatingChangeOut(BaseModel):
    """评级改善：综合等级在同一评级方法下比窗口内最早一个评级日升了几档。"""
    from_grade: str
    to_grade: str
    steps: int                         # 升了几档（A+ 到 F 共 13 档，相邻一档算 1）
    score_delta: float | None = None   # 综合分变化（两边都有分数才有）
    ring_days: int = 0                 # 升档发生在最近多少天内（7 / 30 / 90）
    from_date: str                     # 对比的评级日
    to_date: str                       # 最新评级日


class AnalystChangeOut(BaseModel):
    """评级雷达：窗口内券商的净上调 / 净下调（FMP 个股评级变动；维持评级不算）。"""
    up: int                            # 窗口内上调家数
    down: int                          # 窗口内下调家数
    window_days: int                   # 7 / 30 / 90
    last_date: str                     # 窗口里最近一次上调 / 下调的日期（按这一类的方向）
    firms: list[str] = []              # 最近几家（最多 3 家）
    to_bucket: str = ""                # 最近一次动作的新评级归类：buy / hold / sell


class TrendRadarItem(BaseModel):
    symbol: str
    name: str | None = None
    sector_name: str | None = None
    grade: str | None = None
    kind: Literal["estimates", "estimates_down", "quality", "rating", "rating_down", "analyst_up", "analyst_down"]
    ring_days: int                     # 落在哪一圈：7 / 30 / 90
    strength: float                    # 变化本身：预期 = 该圈变化率；质地 = 改善的百分点合计
    magnitude: float = 1.0             # 变化是入圈门槛的几倍（预期 = 变化率 ÷ 该圈门槛；质地 = 改善百分点 ÷ 利润率门槛），跨圈可比，App 用它定颜色深浅
    good: bool = False                 # 综合等级达到本市场的「好股票」门槛（与信号雷达同一套自适应规则）
    sector: str | None = None          # 信号雷达的行业 key（与雷达顶部行业横条同一套），App 点行业筛选用
    rating: RatingChangeOut | None = None   # kind == rating 时的等级变化
    analyst: AnalystChangeOut | None = None  # kind 为 analyst_up / analyst_down 时的券商评级变动
    facts: TrendFacts


class TrendRadarOut(BaseModel):
    """基本面动向雷达：最近一周 / 一个月 / 三个月里预期上调或质地改善的公司（只陈列事实，不排名次）。"""
    market: str
    as_of: str | None = None
    rings: list[int]
    thresholds: dict[str, float]       # 各圈预期上调门槛与质地改善门槛（推导说明用）
    items: list[TrendRadarItem]
    counts: dict[str, int]             # estimates / quality 各多少；estimates_good / quality_good 是其中达标的
    good_grade: str | None = None      # 「好股票」门槛等级（含）：综合等级不低于它算 good；没有评级时为 None
