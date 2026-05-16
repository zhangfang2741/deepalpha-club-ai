"""ETF 资金流看板 Pydantic schemas。"""

import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class FlowDataPoint(BaseResponse):
    """单只 ETF 某一交易日的资金流数据点。"""

    symbol: str = Field(description="ETF 代码，如 SPY")
    date: datetime.date = Field(description="交易日期")
    close: float = Field(description="收盘价（USD）")
    volume: int = Field(ge=0, description="成交量（股数）")
    dollar_volume: float = Field(description="美元成交量 = volume × close（资金流代理指标）")
    return_pct: float = Field(description="日涨跌幅（%）")


class ETFSummary(BaseResponse):
    """ETF 列表接口中每只 ETF 的汇总数据。"""

    symbol: str
    name: str
    category: str
    current_price: float
    price_change_pct: float = Field(description="所选周期总涨跌幅（%）")
    period_dollar_volume: float = Field(description="所选周期累计美元成交量（USD）")


class ETFFlowsResponse(BaseResponse):
    """GET /etf/flows/{symbol} 响应体。"""

    symbol: str
    name: str
    period: str
    flows: List[FlowDataPoint]


class ETFListResponse(BaseResponse):
    """GET /etf/list 响应体。"""

    period: str
    etfs: List[ETFSummary]


# ── K 线相关 Schema ───────────────────────────────────────────────────────────

class Candle(BaseResponse):
    """单根 K 线数据。"""

    t: str = Field(description="日期，格式 YYYY-MM-DD")
    o: float = Field(description="开盘价")
    h: float = Field(description="最高价")
    l: float = Field(description="最低价")
    c: float = Field(description="收盘价（复权）")
    v: int = Field(description="成交量")


class CandleResponse(BaseResponse):
    """GET /etf/{symbol}/candles 响应体。"""

    symbol: str
    name: str
    candles: List[Candle]


# ── 热力图相关 Schema ──────────────────────────────────────────────────────────

class HeatmapCell(BaseResponse):
    """热力图单元格：某只 ETF 在某日期的标准化强度。"""

    date: str = Field(description="日期标签，格式因粒度而异：day='2026-04-24'，week='2026-W18'，month='2026-04'")
    intensity: Optional[float] = Field(None, description="Z-score 标准化后的资金流强度，None 表示无数据")


class HeatmapETFRow(BaseResponse):
    """热力图中单只 ETF 的一行数据。"""

    symbol: str
    name: str
    cells: List[HeatmapCell]


class HeatmapSectorGroup(BaseResponse):
    """热力图中一个板块的分组数据（含板块均值行和 ETF 明细）。"""

    sector: str = Field(description="板块名称，如 '01 信息技术'")
    avg_cells: List[HeatmapCell] = Field(description="板块内所有 ETF 的强度均值，用于折叠状态展示")
    etfs: List[HeatmapETFRow]


class HeatmapResponse(BaseResponse):
    """GET /etf/heatmap 响应体。"""

    granularity: str = Field(description="粒度：day | week | month")
    days: int = Field(description="请求的交易日数量")
    date_labels: List[str] = Field(description="所有列的日期标签（升序，最新在末尾）")
    sectors: List[HeatmapSectorGroup]


# ── 偏离分相关 Schema ──────────────────────────────────────────────────────────


class ETFDeviationScore(BaseResponse):
    """单只 ETF 的错杀分详情（近期 vs 自身历史基准对比）。"""

    symbol: str
    name: str
    sector: str
    panic_score: Optional[float] = Field(None, description="恐慌期错杀分 = 近期恐慌均值 - 历史恐慌均值，负值=被错杀")
    panic_days: int = Field(0, description="近期恐慌期匹配天数")
    greed_score: Optional[float] = Field(None, description="贪婪期超买分 = 近期贪婪均值 - 历史贪婪均值，正值=被追高")
    greed_days: int = Field(0, description="近期贪婪期匹配天数")
    overall_score: Optional[float] = Field(None, description="综合错位分 = (panic_score + greed_score) / 2，两者任一为 None 则为 None")


class SectorDeviationGroup(BaseResponse):
    """错杀分按板块分组。"""

    sector: str = Field(description="板块名称，如 '01 信息技术'")
    avg_panic_score: Optional[float] = Field(None, description="板块内所有 ETF panic_score 的均值")
    avg_greed_score: Optional[float] = Field(None, description="板块内所有 ETF greed_score 的均值")
    avg_overall_score: Optional[float] = Field(None, description="板块内所有 ETF overall_score 的均值")
    etfs: List[ETFDeviationScore]


class DeviationScoreResponse(BaseResponse):
    """GET /etf/deviation-scores 响应体。"""

    days: int = Field(description="近期窗口交易日数量")
    days_hist: int = Field(description="历史基准窗口交易日数量")
    fg_score: float = Field(description="当前恐惧贪婪指数（0-100）")
    fg_rating: str = Field(description="当前情绪评级，如 'Greed'")
    sectors: List[SectorDeviationGroup]
