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


class SkillRunResponse(BaseModel):
    """Factor time-series produced by executing a Skill."""

    symbol: str
    output_type: str
    factor: list[FactorPoint]
