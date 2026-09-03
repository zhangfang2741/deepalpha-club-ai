"""经纪人（分析师）档案模型。

一个登录账号（User）默认是普通用户；当它拥有一条 Analyst 档案后，
即成为「经纪人」，可以撰写并发布投资报告。user_id 唯一，一人一档。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field

from app.db.base import UUIDModel


def _utcnow() -> datetime:
    """UTC-aware 当前时间。"""
    return datetime.now(UTC)


class Analyst(UUIDModel, table=True):
    """经纪人档案（一人一档，user_id 唯一）。"""

    __tablename__ = "analysts"

    user_id: int = Field(..., unique=True, index=True, nullable=False)
    display_name: str = Field(..., max_length=64, nullable=False)
    bio: str = Field(default="", max_length=2000)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    # 平台是否已认证该经纪人
    verified: bool = Field(default=False, nullable=False)
    # 订阅该经纪人的月费（分），0 表示免费
    monthly_price_cents: int = Field(default=0, nullable=False)
    # active / suspended
    status: str = Field(default="active", max_length=16, index=True, nullable=False)

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
