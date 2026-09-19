"""信号雷达 API schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RadarSignalOut(BaseModel):
    """单只股票在某一天的缠论买卖点信号。"""

    symbol: str = Field(description="股票代码")
    name: str = Field(description="中文名称")
    side: str = Field(description="方向：buy / sell")
    label: str = Field(description="买卖点类型标签，如 一买 / 二卖")
    signal_type: str = Field(description="买卖点类型：buy1/buy2/buy3/sell1/sell2/sell3")
    date: str = Field(description="信号出现日期 YYYY-MM-DD")
    price: float = Field(description="信号价位")
    # 形态技术面强度（0~1）：由缠论多因子加权净值（recommendation.score）归一化而来，
    # 同时驱动前端气泡的大小与颜色深浅。
    strength: float = Field(description="形态技术面强度 0~1，越强越大越深")
    bias: str = Field(description="技术面倾向：bullish / bearish / neutral")
    signal_strength: str = Field(description="买卖点自身强度：strong / medium / weak")
    confirmed: bool = Field(description="信号是否已确认（未确认为右侧预判）")


class RadarDayOut(BaseModel):
    """某一交易日的当日信号快照（前 N 只）。"""

    date: str = Field(description="交易日 YYYY-MM-DD")
    buy_count: int = Field(description="当日买点数量")
    sell_count: int = Field(description="当日卖点数量")
    signals: list[RadarSignalOut] = Field(default_factory=list, description="当日信号，按强度降序")


class SignalRadarResponse(BaseModel):
    """信号雷达响应：某市场最近若干交易日的每日信号。"""

    market: str = Field(description="市场：us / cn / hk")
    etf_name: str = Field(description="扫描所用科技 ETF 名称")
    universe_size: int = Field(description="扫描的成分股数量")
    as_of: str = Field(description="数据生成时间 YYYY-MM-DD")
    top_n: int = Field(description="每日展示的信号条数上限")
    days: list[RadarDayOut] = Field(default_factory=list, description="最近交易日，最新在前")
    status: str = Field(default="ready", description="ready / generating（首次扫描进行中）")
