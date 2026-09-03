"""订阅模型。

两种订阅层级：
- ANALYST：订阅单个经纪人，可见该经纪人的实时报告（analyst_id 指向经纪人）。
- PLATFORM：订阅平台，可见全平台所有报告（analyst_id 为空）。

第一版不接真实支付网关，price_cents 仅作记录占位。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field

from app.db.base import UUIDModel

# 订阅层级
TIER_ANALYST = "ANALYST"
TIER_PLATFORM = "PLATFORM"
VALID_TIERS = (TIER_ANALYST, TIER_PLATFORM)

# 订阅状态
SUB_STATUS_ACTIVE = "ACTIVE"
SUB_STATUS_EXPIRED = "EXPIRED"
SUB_STATUS_CANCELED = "CANCELED"


def _utcnow() -> datetime:
    """UTC-aware 当前时间。"""
    return datetime.now(UTC)


class Subscription(UUIDModel, table=True):
    """一条用户订阅记录。"""

    __tablename__ = "subscriptions"

    user_id: int = Field(..., index=True, nullable=False)
    tier: str = Field(..., max_length=12, index=True, nullable=False)
    # tier=ANALYST 时指向被订阅的经纪人；tier=PLATFORM 时为空
    analyst_id: Optional[UUID] = Field(default=None, index=True)
    status: str = Field(
        default=SUB_STATUS_ACTIVE, max_length=12, index=True, nullable=False
    )
    price_cents: int = Field(default=0, nullable=False)

    start_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    end_at: datetime = Field(  # type: ignore[assignment]
        ...,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
