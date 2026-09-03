"""经纪人（分析师）Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnalystCreate(BaseModel):
    """建档 / 成为经纪人。"""

    display_name: str = Field(..., min_length=1, max_length=64)
    bio: str = Field(default="", max_length=2000)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    monthly_price_cents: int = Field(default=0, ge=0)


class AnalystUpdate(BaseModel):
    """更新经纪人档案。"""

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    bio: Optional[str] = Field(default=None, max_length=2000)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    monthly_price_cents: Optional[int] = Field(default=None, ge=0)


class AnalystStats(BaseModel):
    """经纪人准确率统计。"""

    total_reports: int = 0
    published_reports: int = 0
    resolved_count: int = 0
    correct_count: int = 0
    accuracy: Optional[float] = None
    avg_return_pct: Optional[float] = None


class AnalystOut(BaseModel):
    """经纪人档案输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    display_name: str
    bio: str
    avatar_url: Optional[str]
    verified: bool
    monthly_price_cents: int
    status: str
    created_at: datetime


class AnalystProfileResponse(BaseModel):
    """经纪人主页：档案 + 统计。"""

    analyst: AnalystOut
    stats: AnalystStats


class LeaderboardItem(BaseModel):
    """榜单单行。"""

    analyst: AnalystOut
    stats: AnalystStats


class LeaderboardResponse(BaseModel):
    """准确率榜单。"""

    items: List[LeaderboardItem] = Field(default_factory=list)
    # 只统计已到期报告数 >= min_resolved 的经纪人（样本太少不上榜）
    min_resolved: int = 0
