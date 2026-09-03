"""投资报告 Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.report import (
    VALID_DIRECTIONS,
    VISIBILITY_PUBLIC,
    VISIBILITY_SUBSCRIBER,
)
from app.schemas.astock import KlineBar


class ReportCreate(BaseModel):
    """撰写报告（草稿）。"""

    symbol: str = Field(..., max_length=32)
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(default="", max_length=500)
    content: str = Field(default="")
    direction: str = Field(..., description="BULLISH / BEARISH / NEUTRAL")
    horizon_days: int = Field(..., gt=0, le=1095)
    target_price: Optional[float] = Field(default=None, gt=0)
    visibility: str = Field(default=VISIBILITY_SUBSCRIBER)

    def validate_semantics(self) -> None:
        """业务校验：方向与可见性取值合法。"""
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"direction 必须是 {VALID_DIRECTIONS} 之一")
        if self.visibility not in (VISIBILITY_SUBSCRIBER, VISIBILITY_PUBLIC):
            raise ValueError("visibility 必须是 SUBSCRIBER 或 PUBLIC")


class ReportUpdate(BaseModel):
    """更新草稿（已发布报告不可改核心字段）。"""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = None
    target_price: Optional[float] = Field(default=None, gt=0)
    visibility: Optional[str] = None


class OutcomeOut(BaseModel):
    """回测结果输出。"""

    model_config = ConfigDict(from_attributes=True)

    status: str
    horizon_end_date: str
    price_at_horizon: Optional[float]
    actual_return_pct: Optional[float]
    is_correct: Optional[bool]
    resolved_at: Optional[datetime]


class ReportListItem(BaseModel):
    """列表页报告摘要（始终公开，不含正文）。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analyst_id: UUID
    symbol: str
    symbol_name: str
    title: str
    summary: str
    direction: str
    horizon_days: int
    status: str
    visibility: str
    mark_price: Optional[float]
    mark_date: Optional[str]
    published_at: Optional[datetime]
    created_at: datetime
    outcome: Optional[OutcomeOut] = None


class ReportDetail(BaseModel):
    """报告详情。content 受订阅门控：无权限时置空且 locked=true。"""

    id: UUID
    analyst_id: UUID
    symbol: str
    symbol_name: str
    title: str
    summary: str
    content: str
    direction: str
    horizon_days: int
    target_price: Optional[float]
    status: str
    visibility: str
    mark_price: Optional[float]
    mark_date: Optional[str]
    published_at: Optional[datetime]
    created_at: datetime
    outcome: Optional[OutcomeOut] = None
    locked: bool = False
    # 详情页 K 线：mark_date 前后一段，供前端打标记 + 展示后续走势
    bars: List[KlineBar] = Field(default_factory=list)


class PublishResponse(BaseModel):
    """发布结果。"""

    id: UUID
    status: str
    mark_price: Optional[float]
    mark_date: Optional[str]
    published_at: Optional[datetime]
    outcome: Optional[OutcomeOut] = None


class EvaluateResponse(BaseModel):
    """回测结算结果。"""

    id: UUID
    outcome: OutcomeOut
    message: str = ""


class ReportListResponse(BaseModel):
    """报告流。"""

    items: List[ReportListItem] = Field(default_factory=list)
    total: int = 0
