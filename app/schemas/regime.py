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
