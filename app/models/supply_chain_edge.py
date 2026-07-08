"""Supply-chain graph edge model."""

import uuid

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.db.base import UUIDModel


class SupplyChainEdge(UUIDModel, table=True):
    """A product supply or customer relation."""

    __tablename__ = "supply_chain_edges"  # pyright: ignore[reportAssignmentType]
    edge_id: str = Field(unique=True, index=True)
    src_node_id: str = Field(index=True)
    src_type: str
    dst_node_id: str = Field(index=True)
    dst_type: str
    edge_type: str = Field(index=True)
    timestamp: int
    properties: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    confidence: int = Field(index=True, ge=0, le=100)
    confidence_source: str = Field(default="LLM", index=True)
    last_run_id: uuid.UUID | None = Field(default=None, index=True)
