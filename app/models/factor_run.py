"""换股重跑历史记录。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, UniqueConstraint


class FactorRun(SQLModel, table=True):
    """换股重跑历史记录。"""

    __tablename__ = "factor_runs"
    __table_args__ = (
        UniqueConstraint(
            "skill_id", "user_id", "symbol", "start_date", "end_date", "freq",
            name="uq_factor_run"
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, index=True, nullable=False
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    skill_id: uuid.UUID = Field(..., index=True, nullable=False)
    user_id: int = Field(..., index=True, nullable=False)
    symbol: str = Field(..., max_length=20, nullable=False)
    start_date: str = Field(..., max_length=10, nullable=False)
    end_date: str = Field(..., max_length=10, nullable=False)
    freq: str = Field(default="daily", max_length=10, nullable=False)
    factor_jsonb: object = Field(sa_column=Column(JSON), default_factory=dict)
    narrative_jsonb: object = Field(sa_column=Column(JSON), default=None)