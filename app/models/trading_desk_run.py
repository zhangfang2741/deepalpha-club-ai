"""交易台运行记录。

Redis Stream 存逐 token 事件（TTL 7 天，服务实时与断线重连）；
本表存结构化摘要（turn 级全文），服务历史列表与回放。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlmodel import Column, Field, JSON

from app.db.base import UUIDModel


def _utcnow() -> datetime:
    """UTC-aware 当前时间。供 created_at/updated_at 默认值使用。"""
    return datetime.now(UTC)


class TradingDeskRun(UUIDModel, table=True):
    """一次完整或中断的多 Agent 分析记录。

    Redis Stream 仍持有原始事件；本表只存折叠后的 turns/signals/verdict，
    支撑历史列表（最快数十行 JSON 读出）与回放页（无流式动效直出全文）。

    时间列显式声明 timezone=True：与 alembic 7f27b19b7abd 对齐，
    避免 SQLAlchemy 把带 tz 的 datetime.now(UTC) 编译到 naive 列时报
    asyncpg DataError。
    """

    __tablename__ = "trading_desk_run"

    user_id: int = Field(..., index=True, nullable=False)
    ticker: str = Field(..., index=True, nullable=False)
    trade_date: str = Field(..., max_length=10, nullable=False)
    engine: str = Field(default="", max_length=64)
    status: str = Field(default="running", max_length=16, index=True)

    verdict: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    signals: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    turns: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))

    duration_ms: int = Field(default=0)

    # 三个时间列用 sa_column 显式声明 timezone=True，与 migration 对齐。
    # 用 default_factory=_utcnow 保证 Pydantic 解析时仍带 tz,SQLAlchemy INSERT
    # aware datetime 进 aware 列。
    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True),
    )
