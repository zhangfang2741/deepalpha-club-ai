"""分析师目标价上调 Pydantic schemas."""

from pydantic import Field

from app.schemas.base import BaseResponse


class UpgradeStock(BaseResponse):
    """单只满足上调条件的股票数据."""

    symbol: str
    name: str
    sector: str
    last_month_target: float
    last_quarter_target: float
    last_year_target: float
    all_time_target: float
    last_month_count: int
    month_mom: float
    quarter_yoy: float
    year_vs_all: float


class Nasdaq100UpgradesResponse(BaseResponse):
    """纳斯达克 100 上调筛选结果."""

    as_of: str
    total_constituents: int
    upgrade_count: int
    stocks: list[UpgradeStock]


class PriceTargetQuarter(BaseResponse):
    """单季度平均目标价."""

    label: str = Field(description="季度标签，如 2024 Q1")
    avg_target: float
    count: int


class PriceTargetHistoryResponse(BaseResponse):
    """个股历史目标价季度序列."""

    symbol: str
    quarters: list[PriceTargetQuarter]
