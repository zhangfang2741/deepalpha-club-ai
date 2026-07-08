"""Supply-chain evidence clue model."""

import uuid
from datetime import date

from sqlmodel import Field

from app.db.base import UUIDModel


class SupplyChainClue(UUIDModel, table=True):
    """An append-only evidence fragment with stance."""

    __tablename__ = "supply_chain_clues"  # pyright: ignore[reportAssignmentType]
    edge_id: str | None = Field(default=None, index=True)
    node_id: str | None = Field(default=None, index=True)
    source_type: str = Field(index=True)
    document_url: str = ""
    section: str | None = None
    filing_date: date | None = None
    snippet_text: str
    stance: str = Field(index=True)
    confidence_delta: int | None = None
    run_id: uuid.UUID | None = Field(default=None, index=True)
