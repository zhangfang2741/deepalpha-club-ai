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


class WatchlistPhaseOut(BaseModel):
    """一只自选标的当前的中枢生命周期阶段（见 app/services/chan/pivot_phase.py）。

    结构还没成形（笔数不够）或行情拉取失败时 phase/phase_label 为 None，
    前端按"这条不显示标签"处理，不强行凑一个假阶段。
    """

    symbol: str
    market: str
    phase: str | None = None
    phase_label: str | None = None


class WatchlistPhasesResponse(BaseResponse):
    """自选列表的阶段标签批量响应，key 为 `{market}:{symbol}`。"""

    phases: dict[str, WatchlistPhaseOut]
