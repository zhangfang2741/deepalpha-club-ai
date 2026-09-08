"""APNs 设备 token：一个用户可多设备；locale 决定推送语言。"""

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Column
from sqlalchemy.types import DateTime
from sqlmodel import Field

from app.db.base import UUIDModel


def _utcnow() -> datetime:
    """UTC-aware 当前时间。供 created_at/updated_at 默认值使用。"""
    return datetime.now(UTC)


class DeviceToken(UUIDModel, table=True):
    """用户的 APNs 设备 token（一个用户可绑定多台设备）。

    时间列显式声明 timezone=True（timestamptz）：本表经异步 asyncpg 写入
    （API 层 upsert），UUIDModel 默认的 aware datetime 写 naive 列会直接
    抛 asyncpg DataError。
    """

    __tablename__ = "device_token"

    user_id: int = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True, unique=True, description="APNs hex device token")
    platform: str = Field(default="ios")
    locale: str = Field(default="zh-Hans", description="zh-Hans / en")
    last_user_id: Optional[int] = None

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
