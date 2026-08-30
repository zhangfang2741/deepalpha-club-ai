"""交易台运行记录。

Redis Stream 存逐 token 事件（TTL 7 天，服务实时与断线重连）；
本表存结构化摘要（turn 级全文），服务历史列表与回放。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Column, Field, JSON

from app.db.base import UUIDModel


class TradingDeskRun(UUIDModel, table=True):
    """一次完整或中断的多 Agent 分析记录。

    Redis Stream 仍持有原始事件；本表只存折叠后的 turns/signals/verdict，
    支撑历史列表（最快数十行 JSON 读出）与回放页（无流式动效直出全文）。
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
    finished_at: datetime | None = Field(default=None)
