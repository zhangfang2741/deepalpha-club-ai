"""每日晨报表：market+trade_date 唯一，幂等与回退都依赖它。"""

from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field

from app.db.base import UUIDModel


class MorningReport(UUIDModel, table=True):
    """每日晨报（每个 market + trade_date 唯一一行）。"""

    __tablename__ = "morning_report"

    market: str = Field(index=True, description="us / cn / hk")
    trade_date: date = Field(index=True)
    status: str = Field(default="generating", description="generating / success / failed")
    content: dict = Field(default_factory=dict, sa_column=Column(JSON))
    generated_at: Optional[datetime] = None
    model_name: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    __table_args__ = (
        UniqueConstraint("market", "trade_date", name="uq_morning_report_market_date"),
    )


def utc_now() -> datetime:
    """返回当前 UTC 时间（供生成/推送任务写时间戳时统一使用）。"""
    return datetime.now(UTC)
