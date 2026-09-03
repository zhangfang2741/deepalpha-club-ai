"""订阅 Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.subscription import TIER_ANALYST, TIER_PLATFORM, VALID_TIERS


class SubscriptionCreate(BaseModel):
    """创建订阅。"""

    tier: str = Field(..., description="ANALYST / PLATFORM")
    analyst_id: Optional[UUID] = Field(default=None, description="tier=ANALYST 时必填")
    months: int = Field(default=1, ge=1, le=36, description="订阅时长（月）")

    def validate_semantics(self) -> None:
        """业务校验：层级合法、ANALYST 必带 analyst_id。"""
        if self.tier not in VALID_TIERS:
            raise ValueError(f"tier 必须是 {VALID_TIERS} 之一")
        if self.tier == TIER_ANALYST and self.analyst_id is None:
            raise ValueError("订阅经纪人（ANALYST）必须提供 analyst_id")
        if self.tier == TIER_PLATFORM and self.analyst_id is not None:
            raise ValueError("订阅平台（PLATFORM）不应提供 analyst_id")


class SubscriptionOut(BaseModel):
    """订阅输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    tier: str
    analyst_id: Optional[UUID]
    status: str
    price_cents: int
    start_at: datetime
    end_at: datetime


class SubscriptionListResponse(BaseModel):
    """我的订阅列表。"""

    items: List[SubscriptionOut] = Field(default_factory=list)
