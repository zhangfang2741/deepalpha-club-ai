"""行业（板块）级市场状态因子表。

每个 GICS 板块独立拟合 HMM，逐交易日输出该板块的逐利/观望/避险后验与因子权重。
业务唯一键为 (trade_date, sector)。
"""
from __future__ import annotations

from sqlmodel import Field, UniqueConstraint

from app.db.base import UUIDModel


class RegimeSectorFeatures(UUIDModel, table=True):
    """逐交易日 × 板块 的市场状态特征与后验。"""

    __tablename__ = "regime_sector_features"
    __table_args__ = (
        UniqueConstraint("trade_date", "sector", name="uq_regime_sector"),
    )

    trade_date: str = Field(..., max_length=10, index=True, nullable=False)
    sector: str = Field(..., max_length=30, index=True, nullable=False)

    # 信号层特征
    sector_ret: float | None = Field(default=None)
    sector_vol: float | None = Field(default=None)
    vix: float | None = Field(default=None)
    rs_vs_market: float | None = Field(default=None)
    sector_cmf: float | None = Field(default=None)

    # 状态层：HMM 滤波后验
    p_risk_on: float | None = Field(default=None)
    p_neutral: float | None = Field(default=None)
    p_risk_off: float | None = Field(default=None)

    regime_label: str | None = Field(default=None, max_length=20)
    confirmed_label: str | None = Field(default=None, max_length=20)
    params_version: str | None = Field(default=None, max_length=10)

    # 应用层：下游因子动态权重乘子 = 1 − p_避险
    factor_weight: float | None = Field(default=None)
