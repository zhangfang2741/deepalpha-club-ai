"""每日晨报表：market+trade_date 唯一，幂等与回退都依赖它。"""

from datetime import UTC, date, datetime
from typing import ClassVar, Optional

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.types import JSON, DateTime
from sqlmodel import Field

from app.db.base import UUIDModel


def _utcnow() -> datetime:
    """UTC-aware 当前时间。供 created_at/updated_at 默认值使用。"""
    return datetime.now(UTC)


class MorningReport(UUIDModel, table=True):
    """每日晨报（每个 market + trade_date 唯一一行）。

    时间列显式声明 timezone=True（timestamptz），与 trading_desk_run 的先例
    一致：UUIDModel 默认值是 aware datetime，写 naive 列在 asyncpg 下会抛
    DataError（同步 psycopg 宽容但语义混乱）。
    """

    # SQLModel 将表名同时声明为 ClassVar 和 declared_attr；字符串覆盖是 ORM 支持的用法。
    __tablename__: ClassVar[str] = "morning_report"  # pyright: ignore[reportIncompatibleVariableOverride]

    market: str = Field(index=True, description="us / cn / hk")
    trade_date: date = Field(index=True)
    status: str = Field(default="generating", description="generating / success / failed")
    content: dict = Field(default_factory=dict, sa_column=Column(JSON))
    model_name: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
    generated_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    __table_args__ = (
        UniqueConstraint("market", "trade_date", name="uq_morning_report_market_date"),
    )
