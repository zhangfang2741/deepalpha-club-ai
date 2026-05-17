"""Request and response schemas for the Skill factor explorer."""

from typing import Literal

from pydantic import BaseModel, Field


class SkillMessage(BaseModel):
    """Single message in the Skill generation conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class SkillGenerateRequest(BaseModel):
    """Request body for streaming Skill code generation."""

    messages: list[SkillMessage] = Field(..., min_length=1, max_length=40)


class SkillGenerateResponse(BaseModel):
    """Single SSE chunk from the Skill generation stream."""

    content: str = ""
    done: bool = False


class KlineBar(BaseModel):
    """OHLCV candlestick bar for a single time period."""

    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class KlineResponse(BaseModel):
    """Candlestick data response for a symbol."""

    symbol: str
    freq: str
    klines: list[KlineBar]


class FactorPoint(BaseModel):
    """Single factor value at a specific date."""

    time: str
    value: float


class SkillRunRequest(BaseModel):
    """Request body for executing a Skill against historical data."""

    code: str = Field(..., max_length=20000)
    symbol: str = Field(..., min_length=1, max_length=20)
    start_date: str
    end_date: str
    freq: Literal["daily", "weekly"] = "daily"
    include_news: bool = False  # 舆情因子
    include_financials: bool = False  # 财务/分析师预测数据


class SkillRunResponse(BaseModel):
    """Factor time-series produced by executing a Skill."""

    symbol: str
    output_type: str
    factor: list[FactorPoint]


from uuid import UUID
from datetime import datetime


class FactorSkillBrief(BaseModel):
    id: UUID
    title: str
    description: str
    category: str
    default_symbol: str
    is_public: bool
    pin_priority: int | None = None
    created_at: datetime


class FactorSkillDetail(FactorSkillBrief):
    code: str
    default_start_date: str
    default_end_date: str
    default_freq: str
    snapshot: dict
    narrative: dict | None = None
    owner_id: int | None = None


class FactorSkillGalleryResponse(BaseModel):
    hero: FactorSkillDetail | None = None
    cases: list[FactorSkillBrief] = []


class FactorSkillMineResponse(BaseModel):
    skills: list[FactorSkillBrief] = []


class SaveSkillRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., max_length=30)
    code: str = Field(..., max_length=20000)
    symbol: str = Field(..., max_length=20)
    start_date: str = Field(..., max_length=10)
    end_date: str = Field(..., max_length=10)
    freq: Literal["daily", "weekly"] = "daily"


class RerunRequest(BaseModel):
    symbol: str = Field(..., max_length=20)
    start_date: str = Field(..., max_length=10)
    end_date: str = Field(..., max_length=10)
    freq: Literal["daily", "weekly"] = "daily"
