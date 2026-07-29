"""市场状态（regime）日频因子表。

「算一次，双消费」：既供研究员看的状态监控面板，又把 regime 后验概率作为因子
写入本表，供下游因子动态加权（如 动量权重 ×(1−p_避险)）。
"""
from __future__ import annotations

from sqlmodel import Field

from app.db.base import UUIDModel


class RegimeFeatures(UUIDModel, table=True):
    """逐交易日的市场状态特征与后验（因子表）。"""

    __tablename__ = "regime_features"

    # 交易日（YYYY-MM-DD），业务唯一键
    trade_date: str = Field(..., max_length=10, index=True, unique=True, nullable=False)

    # 信号层特征
    qqq_return: float | None = Field(default=None)
    realized_vol: float | None = Field(default=None)
    vix: float | None = Field(default=None)
    ods: float | None = Field(default=None)
    cf: float | None = Field(default=None)

    # 量价确认（真实 OBV 斜率 / CMF）
    obv_slope: float | None = Field(default=None)
    cmf: float | None = Field(default=None)

    # 状态层：HMM 滤波后验
    p_risk_on: float | None = Field(default=None)
    p_neutral: float | None = Field(default=None)
    p_risk_off: float | None = Field(default=None)

    # argmax 原始标签 / 「持续 N 日」确认标签 / 参数版本（月末冻结日）
    regime_label: str | None = Field(default=None, max_length=20)
    confirmed_label: str | None = Field(default=None, max_length=20)
    params_version: str | None = Field(default=None, max_length=10)

    # 应用层：下游因子动态权重乘子 = 1 − p_避险
    factor_weight: float | None = Field(default=None)
