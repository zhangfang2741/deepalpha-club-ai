"""投资报告与其回测结果模型。

Report：经纪人针对某只 A 股标的撰写的投资报告，声明方向 + 时限；
发布（publish）时平台记录「标记点」mark_price / mark_date（当时收盘价与交易日）。

ReportOutcome：报告到期后的回测结果（可重算的派生数据，独立成表，
口径调整时可整表重算而不动原始报告）。report_id 唯一，一篇报告一条结算。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel

# 报告方向
DIRECTION_BULLISH = "BULLISH"
DIRECTION_BEARISH = "BEARISH"
DIRECTION_NEUTRAL = "NEUTRAL"
VALID_DIRECTIONS = (DIRECTION_BULLISH, DIRECTION_BEARISH, DIRECTION_NEUTRAL)

# 报告状态
REPORT_STATUS_DRAFT = "DRAFT"
REPORT_STATUS_PUBLISHED = "PUBLISHED"

# 报告可见性
VISIBILITY_SUBSCRIBER = "SUBSCRIBER"
VISIBILITY_PUBLIC = "PUBLIC"

# 回测状态
OUTCOME_STATUS_PENDING = "PENDING"
OUTCOME_STATUS_RESOLVED = "RESOLVED"


def _utcnow() -> datetime:
    """UTC-aware 当前时间。"""
    return datetime.now(UTC)


class Report(UUIDModel, table=True):
    """经纪人的一篇投资报告。"""

    __tablename__ = "reports"

    analyst_id: UUID = Field(..., index=True, nullable=False)
    symbol: str = Field(..., max_length=16, index=True, nullable=False)
    symbol_name: str = Field(default="", max_length=64)
    title: str = Field(..., max_length=200, nullable=False)
    summary: str = Field(default="", max_length=500)
    content: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))

    direction: str = Field(..., max_length=8, index=True, nullable=False)
    horizon_days: int = Field(..., nullable=False)
    target_price: Optional[float] = Field(default=None)

    status: str = Field(
        default=REPORT_STATUS_DRAFT, max_length=12, index=True, nullable=False
    )
    visibility: str = Field(default=VISIBILITY_SUBSCRIBER, max_length=12, nullable=False)

    # 发布时打的 K 线标记：当时收盘价与交易日
    mark_price: Optional[float] = Field(default=None)
    mark_date: Optional[str] = Field(default=None, max_length=10, index=True)

    published_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )


class ReportOutcome(UUIDModel, table=True):
    """一篇报告的回测结果（report_id 唯一）。"""

    __tablename__ = "report_outcomes"
    __table_args__ = (
        UniqueConstraint("report_id", name="uq_report_outcome_report"),
    )

    report_id: UUID = Field(..., index=True, nullable=False)
    status: str = Field(
        default=OUTCOME_STATUS_PENDING, max_length=12, index=True, nullable=False
    )
    horizon_end_date: str = Field(..., max_length=10, nullable=False)
    price_at_horizon: Optional[float] = Field(default=None)
    actual_return_pct: Optional[float] = Field(default=None)
    is_correct: Optional[bool] = Field(default=None)
    resolved_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
