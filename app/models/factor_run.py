"""换股重跑历史记录。"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


class FactorRun(UUIDModel, table=True):
    """换股重跑历史记录。"""

    __tablename__ = "factor_runs"
    __table_args__ = (
        UniqueConstraint(
            "skill_id", "user_id", "symbol", "start_date", "end_date", "freq",
            name="uq_factor_run"
        ),
    )

    skill_id: uuid.UUID = Field(..., index=True, nullable=False)
    user_id: int = Field(..., index=True, nullable=False)
    symbol: str = Field(..., max_length=20, nullable=False)
    start_date: str = Field(..., max_length=10, nullable=False)
    end_date: str = Field(..., max_length=10, nullable=False)
    freq: str = Field(default="daily", max_length=10, nullable=False)
    factor_jsonb: object = Field(sa_column=Column(JSON), default_factory=dict)
    narrative_jsonb: object = Field(sa_column=Column(JSON), default=None)
