"""ETF 资金流看板 Pydantic schemas。"""

import datetime
from typing import List

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
