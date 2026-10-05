"""A 股 / 港股行业（申万 / 恒生一级）状态因子表。

与美股的 `regime_sector_features` 同一套字段，多一个 market 列，行业 key 是中文行业名；
业务唯一键为 (market, sector, trade_date)。行业指数是市值最大的几只成分股的等权合成（见 regime/cnhk_sector.py）。
"""
from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


class RegimeMarketSectorFeatures(UUIDModel, table=True):
    """逐交易日 × 行业 的 A 股 / 港股市场状态特征与后验。"""

    __tablename__ = "regime_market_sector_features"
    __table_args__ = (UniqueConstraint("market", "sector", "trade_date", name="uq_regime_market_sector"),)

    market: str = Field(..., max_length=8, index=True, nullable=False)
    sector: str = Field(..., max_length=30, index=True, nullable=False)
    trade_date: str = Field(..., max_length=10, index=True, nullable=False)

    sector_ret: float | None = Field(default=None)
    sector_vol: float | None = Field(default=None)
    vol_ratio: float | None = Field(default=None)
    rs_vs_market: float | None = Field(default=None)
    sector_cmf: float | None = Field(default=None)

    p_risk_on: float | None = Field(default=None)
    p_neutral: float | None = Field(default=None)
    p_risk_off: float | None = Field(default=None)

    regime_label: str | None = Field(default=None, max_length=20)
    confirmed_label: str | None = Field(default=None, max_length=20)
    params_version: str | None = Field(default=None, max_length=10)
