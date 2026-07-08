"""Supply-chain graph API schemas."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    """Create a universe run."""

    universe: str = "sp500"
    params: dict[str, Any] = Field(default_factory=dict)


class RunCreated(BaseModel):
    """Created run identity."""

    run_id: uuid.UUID
    status: str
