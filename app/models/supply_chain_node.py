"""Supply-chain graph node model."""

import uuid

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.db.base import UUIDModel


class SupplyChainNode(UUIDModel, table=True):
    """A company or supplier node."""

    __tablename__ = "supply_chain_nodes"  # pyright: ignore[reportAssignmentType]
    node_id: str = Field(unique=True, index=True)
    node_type: str = Field(index=True)
    name: str = Field(index=True)
    properties: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    first_seen_run_id: uuid.UUID | None = Field(default=None, index=True)
