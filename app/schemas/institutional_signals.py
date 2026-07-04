"""机构资金信号（Institutional Signals）Pydantic schemas。

产品只对外暴露「状态 + 五维评分 + 证据链」，原始数据折叠在 signals 明细里。
"""
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse

# 五个维度的稳定 key，与 dimensions.py 一一对应
DIMENSION_KEYS = ("expectation", "positioning", "participation", "fundamental", "confirmation")


class SignalExplanation(BaseResponse):
    """单条信号的完整解释：原始数据 → 计算式 → 判定规则 → 结论。"""

    inputs: List[str] = Field(default_factory=list, description="原始数据，如 [近月均值=$185.2（41家）, 近季均值=$182.3]")
    formula: Optional[str] = Field(None, description="计算式，如 (185.2−182.3)/182.3×100 = +1.6%")
    thresholds: Optional[str] = Field(None, description="判定规则/阈值")
    conclusion: Optional[str] = Field(None, description="结论：为何是这个方向/是否命中/加减分")
    source: Optional[str] = Field(None, description="数据来源，如 FMP price-target-summary")


class SignalItem(BaseResponse):
    """单条底层信号（如 Relative Volume、Target Price）。"""

    key: str = Field(description="稳定标识，如 relative_volume / target_price")
    label: str = Field(description="中文名，如 相对成交量")
    value: Optional[str] = Field(None, description="展示值，如 2.1x / +3.4%")
    direction: str = Field("flat", description="方向：up / down / flat")
    hit: bool = Field(False, description="是否触发（用于状态组合判定）")
    detail: Optional[str] = Field(None, description="补充说明（一句话口径）")
    explain: Optional[SignalExplanation] = Field(None, description="完整解释：原始数据/计算/判定/结论")


class DimensionScore(BaseResponse):
    """五维之一的评分与明细。"""

    key: str = Field(description="维度 key，见 DIMENSION_KEYS")
    label: str = Field(description="维度中文名，如 预期")
    question: str = Field(description="该维度回答的核心问题")
    score: float = Field(ge=0, le=100, description="子分 0–100")
    status: str = Field("ok", description="ok / partial / unavailable")
    signals: List[SignalItem] = Field(default_factory=list)


class SignalState(BaseResponse):
    """由维度组合推导出的状态标签（如 机构建仓 / 趋势确认）。"""

    key: str = Field(description="状态 key，如 expectation_upgrade")
    emoji: str
    label: str = Field(description="状态中文名")
    stars: int = Field(ge=1, le=5, description="重要度星级")
    meaning: str = Field(description="一句话含义")
    logic: Optional[str] = Field(None, description="触发逻辑（判定规则，可展示）")
    evidence: List[str] = Field(default_factory=list, description="命中的证据链")
    # 买入视角元数据（仅偏多状态有值）
    buy_rank: Optional[int] = Field(None, description="买入价值排序，1=最佳入场")
    buy_timing: Optional[str] = Field(None, description="时机：启动前 / 早中段 / 中段 / 偏晚")
    buy_edge: Optional[str] = Field(None, description="优势：赔率最好 / 胜率最高 / 最扛跌 …")
    buy_thesis: Optional[str] = Field(None, description="买入逻辑一句话")


class BuyStage(BaseResponse):
    """买入视角阶梯的一档（早→晚），active 表示当前是否命中。"""

    key: str
    emoji: str
    label: str
    timing: str
    edge: str
    thesis: str
    rank: int
    active: bool


class LeaderboardEntry(BaseResponse):
    """榜单单行：一支标的的扫描摘要（不含期权，点进详情页看完整五维）。"""

    symbol: str
    name: str
    composite_score: float = Field(ge=0, le=100)
    coverage: int = Field(ge=0, le=5)
    confidence: str
    top_state: Optional[SignalState] = Field(None, description="最强的非中性状态")
    states: List[SignalState] = Field(default_factory=list)
    dimension_scores: dict = Field(default_factory=dict, description="各维度 key → 分数")


class LeaderboardResponse(BaseResponse):
    """GET /api/v1/institutional-signals/leaderboard 响应。"""

    status: str = Field(default="ready", description="ready（有数据）/ computing（后台扫描中）")
    as_of: str = ""
    computed_at: str = Field(default="", description="扫描完成时间 ISO")
    universe_source: str = Field(default="", description="universe 来源：sp500 / fallback")
    universe_size: int = Field(default=0, description="扫描的股票总数")
    scanned: int = Field(default=0, description="成功评分的股票数")
    note: str = Field(default="", description="口径说明")
    entries: List[LeaderboardEntry] = Field(default_factory=list)


class InstitutionalSignalReport(BaseResponse):
    """GET /api/v1/institutional-signals?symbol= 完整响应。"""

    symbol: str
    name: str
    as_of: str = Field(description="报告日期 YYYY-MM-DD")
    composite_score: float = Field(ge=0, le=100,
                                   description="五维加权综合分（缺失维度按中性 50 计入，不剔除）")
    coverage: int = Field(ge=0, le=5, description="已接入数据的维度数（ok/partial）")
    coverage_total: int = Field(default=5, description="维度总数")
    confidence: str = Field(description="置信度：高 / 中 / 低（由覆盖度决定）")
    headline: str = Field(description="一句话结论")
    buy_headline: str = Field(default="", description="买入视角一句话结论")
    buy_ladder: List[BuyStage] = Field(default_factory=list, description="买入视角阶梯（早→晚）")
    price_history: List[float] = Field(default_factory=list, description="近期收盘价（sparkline 用）")
    dimensions: List[DimensionScore]
    states: List[SignalState]
