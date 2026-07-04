"""机构资金信号（Institutional Signals）Pydantic schemas。

产品只对外暴露「状态 + 五维评分 + 证据链」，原始数据折叠在 signals 明细里。
"""
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse

# 五个维度的稳定 key，与 dimensions.py 一一对应
DIMENSION_KEYS = ("expectation", "positioning", "participation", "fundamental", "confirmation")


class SignalItem(BaseResponse):
    """单条底层信号（如 Relative Volume、Target Price）。"""

    key: str = Field(description="稳定标识，如 relative_volume / target_price")
    label: str = Field(description="中文名，如 相对成交量")
    value: Optional[str] = Field(None, description="展示值，如 2.1x / +3.4%")
    direction: str = Field("flat", description="方向：up / down / flat")
    hit: bool = Field(False, description="是否触发（用于状态组合判定）")
    detail: Optional[str] = Field(None, description="补充说明")


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
    evidence: List[str] = Field(default_factory=list, description="命中的证据链")


class InstitutionalSignalReport(BaseResponse):
    """GET /api/v1/institutional-signals?symbol= 完整响应。"""

    symbol: str
    name: str
    as_of: str = Field(description="报告日期 YYYY-MM-DD")
    composite_score: float = Field(ge=0, le=100, description="五维加权综合分")
    headline: str = Field(description="一句话结论")
    dimensions: List[DimensionScore]
    states: List[SignalState]
