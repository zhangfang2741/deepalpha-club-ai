"""市场状态监控（regime）Pydantic schemas。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class RegimePoint(BaseResponse):
    """单交易日的市场状态记录（信号 + 后验 + 因子权重）。"""

    trade_date: str = Field(description="交易日 YYYY-MM-DD")
    qqq_return: Optional[float] = Field(None, description="纳指滚动收益")
    realized_vol: Optional[float] = Field(None, description="已实现波动（年化）")
    vix: Optional[float] = Field(None, description="VIX 收盘")
    ods: Optional[float] = Field(None, description="进攻-防御相对强弱（滚动窗口）")
    cf: Optional[float] = Field(None, description="现金相对风险资产强弱（滚动窗口）")
    obv_slope: Optional[float] = Field(None, description="OBV 归一化斜率（量能确认）")
    cmf: Optional[float] = Field(None, description="Chaikin Money Flow（量价确认）")
    p_risk_on: Optional[float] = Field(None, description="逐利后验")
    p_neutral: Optional[float] = Field(None, description="观望后验")
    p_risk_off: Optional[float] = Field(None, description="避险后验")
    regime_label: Optional[str] = Field(None, description="argmax 原始状态")
    confirmed_label: Optional[str] = Field(None, description="连续 N 日确认后的状态")
    params_version: Optional[str] = Field(None, description="HMM 参数版本（月末冻结日）")
    factor_weight: Optional[float] = Field(None, description="下游因子权重乘子 = 1 − p_避险")


class RegimeResponse(BaseResponse):
    """GET /api/v1/regime 面板响应。"""

    latest: Optional[RegimePoint] = Field(None, description="最新交易日状态")
    history: List[RegimePoint] = Field(default_factory=list)


class RegimeStageResult(BaseResponse):
    """POST /api/v1/regime/run 触发 pipeline 阶段的结果。"""

    rows: int
    written: int
    latest_date: Optional[str] = None
    latest_label: Optional[str] = None
    latest_factor_weight: Optional[float] = None


class SectorRegimePoint(BaseResponse):
    """单个板块单交易日的状态记录。"""

    trade_date: str
    sector: str = Field(description="板块 key，如 technology")
    sector_name: str = Field(description="板块中文名，如 科技")
    sector_ret: Optional[float] = None
    sector_vol: Optional[float] = None
    vix: Optional[float] = None
    rs_vs_market: Optional[float] = Field(None, description="相对大盘滚动强弱")
    sector_cmf: Optional[float] = None
    p_risk_on: Optional[float] = None
    p_neutral: Optional[float] = None
    p_risk_off: Optional[float] = None
    regime_label: Optional[str] = None
    confirmed_label: Optional[str] = None
    params_version: Optional[str] = None
    factor_weight: Optional[float] = None


class SectorRegimeLatest(BaseResponse):
    """GET /api/v1/regime/sectors：各板块最新状态 + 可选历史。"""

    trade_date: Optional[str] = None
    sectors: List[SectorRegimePoint] = Field(default_factory=list)


class SectorRegimeHistory(BaseResponse):
    """GET /api/v1/regime/sectors/{sector}：单板块历史序列。"""

    sector: str
    sector_name: str
    history: List[SectorRegimePoint] = Field(default_factory=list)


class SectorStageResult(BaseResponse):
    """POST /api/v1/regime/sectors/run 结果。"""

    sectors: int
    written: int
