"""日 K 线缓存模型（symbol + date 唯一，每标的每交易日一行）。

数据来自东方财富行情接口（前复权），落库做缓存：减少对外请求、
支撑报告回测（取到期日收盘价）与详情页 K 线渲染。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


def _utcnow() -> datetime:
    """UTC-aware 当前时间。"""
    return datetime.now(UTC)


class PriceBar(UUIDModel, table=True):
    """单标的单交易日的前复权日 K 线。"""

    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_price_bar_symbol_date"),
    )

    symbol: str = Field(..., max_length=16, index=True, nullable=False)
    date: str = Field(..., max_length=10, index=True, nullable=False)
    open: float = Field(..., nullable=False)
    high: float = Field(..., nullable=False)
    low: float = Field(..., nullable=False)
    close: float = Field(..., nullable=False)
    volume: float = Field(default=0.0, nullable=False)

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
