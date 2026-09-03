"""A 股行情/基本面 Pydantic schemas。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KlineBar(BaseModel):
    """单根日 K 线。"""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class KlineResponse(BaseModel):
    """K 线响应。"""

    symbol: str
    bars: List[KlineBar] = Field(default_factory=list)


class QuoteResponse(BaseModel):
    """实时快照。"""

    symbol: str
    name: str = ""
    price: Optional[float] = None
    change_pct: Optional[float] = None
    change: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    market_cap: Optional[float] = None


class FundamentalResponse(BaseModel):
    """基本面/关键指标。"""

    symbol: str
    profile: Dict[str, Any] = Field(default_factory=dict)
    indicators: Dict[str, Any] = Field(default_factory=dict)
