"""宏观环境 / 市场概览 API schemas（雷达页顶部「宏观 / 行业」两格及其弹层）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MacroStateOut(BaseModel):
    """大盘市场状态（逐利 / 观望 / 避险）。"""

    label: str = Field(description="risk_on / neutral / risk_off")
    label_text: str = Field(description="状态展示名，如 逐利")
    probability: float = Field(description="当前状态的后验概率 0~1")
    p_risk_on: float
    p_neutral: float
    p_risk_off: float
    days_in_state: int = Field(description="当前状态已连续多少个交易日")
    as_of: str = Field(description="交易日 YYYY-MM-DD")


class MacroStatePoint(BaseModel):
    """状态色带上的一天。"""

    date: str
    label: str | None = Field(default=None, description="确认后的状态；样本不足时为空")


class MacroDriverOut(BaseModel):
    """一个宏观驱动因素。"""

    key: str
    name: str
    value: float | None = Field(default=None, description="当前值；按涨跌幅展示的因素为空")
    unit: str = Field(description="percent（利率等，单位 %）/ point（指数点）/ change（只展示涨跌幅）")
    change: float | None = Field(default=None, description="近 20 个交易日变化：percent=基点，point=点，change=%")
    direction: str | None = Field(default=None, description="up / down / flat；数据不足为空")
    impact: str = Field(description="对股票的影响：positive / negative / neutral")
    text: str = Field(description="一句大白话解读")
    as_of: str | None = None


class MacroEventOut(BaseModel):
    """宏观日历上的一个事件（时间已换成该市场本地时区）。"""

    date: str = Field(description="本地日期 YYYY-MM-DD")
    time: str = Field(description="本地时间 HH:MM")
    country: str = Field(description="US / CN")
    name: str
    importance: int = Field(description="1~3，3 最重要")


class MacroResponse(BaseModel):
    """宏观弹层。"""

    market: str
    available: bool = Field(description="该市场宏观数据是否已上线")
    state: MacroStateOut | None = None
    history: list[MacroStatePoint] = Field(default_factory=list, description="近一年状态，升序")
    drivers: list[MacroDriverOut] = Field(default_factory=list)
    events: list[MacroEventOut] = Field(default_factory=list, description="未来 7 天，按时间升序")


class SectorBriefOut(BaseModel):
    """行业格里的一个行业。"""

    key: str
    name: str
    rs_vs_market: float | None = None
    label: str | None = Field(default=None, description="确认后的状态 risk_on / neutral / risk_off")


class MarketOverviewResponse(BaseModel):
    """雷达页顶部宏观格 + 行业格摘要（情绪格仍走 /panic-index）。"""

    market: str
    available: bool = Field(description="该市场宏观 / 行业数据是否已上线")
    macro_state: MacroStateOut | None = None
    next_event: MacroEventOut | None = None
    strongest: SectorBriefOut | None = None
    weakest: SectorBriefOut | None = None
    sectors_as_of: str | None = None


class SectorRowOut(BaseModel):
    """行业弹层的一行。"""

    key: str
    name: str
    rs_vs_market: float | None = None
    label: str | None = None
    p_risk_on: float | None = None
    has_children: bool = False
    buy_count: int = 0
    sell_count: int = 0


class SectorBoardResponse(BaseModel):
    """行业弹层：各行业按相对强弱从强到弱 + 宽基雷达当日按行业的买卖点数。"""

    market: str
    available: bool
    as_of: str | None = None
    radar_universe: str | None = Field(default=None, description="买卖点统计所用的宽基 universe 键，如 sp500")
    radar_universe_name: str | None = None
    radar_date: str | None = Field(default=None, description="买卖点统计对应的雷达交易日")
    sectors: list[SectorRowOut] = Field(default_factory=list)
    children_of: str | None = Field(default=None, description="下钻时为一级行业 key")
