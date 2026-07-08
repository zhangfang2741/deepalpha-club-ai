"""Supply-chain batch run model."""

from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.db.base import UUIDModel


class SupplyChainRun(UUIDModel, table=True):
    """A single-company or universe run."""

    __tablename__ = "supply_chain_runs"  # pyright: ignore[reportAssignmentType]
    run_type: str
    universe: str
    status: str = Field(default="pending", index=True)
    total: int = 0
    completed: int = 0
    failed: int = 0
    params: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    quota_paused_at: datetime | None = None
    resume_after: datetime | None = None
    probe_attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
