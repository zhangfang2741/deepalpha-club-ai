"""自选股 API schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class WatchlistAddRequest(BaseModel):
    """加入自选的请求体。

    市场由客户端显式传入，不做自动猜测（同 A 股/港股代码形态有歧义的既有约定，
    见 ChanViewModel 的 apply(market:, symbol:)）。
    """

    market: str = Field(pattern="^(us|cn|hk)$", description="市场：us / cn / hk")
    symbol: str = Field(min_length=1, description="裸代码，不带市场后缀")
    name: str = Field(min_length=1, description="展示用名称")


class WatchlistItemOut(BaseResponse):
    """一条自选记录。"""

    market: str
    symbol: str
    name: str
    created_at: datetime


class WatchlistResponse(BaseResponse):
    """自选列表响应。"""

    items: list[WatchlistItemOut]
