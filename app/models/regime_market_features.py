"""A 股 / 港股大盘状态（regime）日频因子表。

与美股的 `regime_features`（只有 trade_date 一个业务键）同一套字段，多一个 market 列：
同一条管线（三篮子 ODS/CF → 走-前向 HMM），只是换成各自市场的 ETF 篮子，所以另起一张表，
不动美股表的唯一键与既有查询。`vix` 在这里是「短期 / 长期已实现波动比」（两个市场没有可用的波动率指数）。
"""
from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


class RegimeMarketFeatures(UUIDModel, table=True):
    """逐交易日的 A 股 / 港股市场状态特征与后验。"""

    __tablename__ = "regime_market_features"
    __table_args__ = (UniqueConstraint("market", "trade_date", name="uq_regime_market_date"),)

    market: str = Field(..., max_length=8, index=True, nullable=False)
    trade_date: str = Field(..., max_length=10, index=True, nullable=False)

    benchmark_return: float | None = Field(default=None)
    realized_vol: float | None = Field(default=None)
    vol_ratio: float | None = Field(default=None)
    ods: float | None = Field(default=None)
    cf: float | None = Field(default=None)
    obv_slope: float | None = Field(default=None)
    cmf: float | None = Field(default=None)

    p_risk_on: float | None = Field(default=None)
    p_neutral: float | None = Field(default=None)
    p_risk_off: float | None = Field(default=None)

    regime_label: str | None = Field(default=None, max_length=20)
    confirmed_label: str | None = Field(default=None, max_length=20)
    params_version: str | None = Field(default=None, max_length=10)
