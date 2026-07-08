"""Supply-chain company task model."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.db.base import UUIDModel


class SupplyChainTask(UUIDModel, table=True):
    """One company within a graph run."""

    __tablename__ = "supply_chain_tasks"  # pyright: ignore[reportAssignmentType]
    run_id: uuid.UUID = Field(index=True, foreign_key="supply_chain_runs.id")
    ticker: str = Field(index=True)
    stage: str = "DISCOVER"
    status: str = Field(default="queued", index=True)
    retries: int = 0
    max_retries: int = 3
    quota_retries: int = 0
    celery_task_id: str | None = None
    error: str | None = None
    resume_after: datetime | None = None
    result_summary: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    started_at: datetime | None = None
    finished_at: datetime | None = None
