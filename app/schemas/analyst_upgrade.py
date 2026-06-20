"""分析师目标价上调 Pydantic schemas."""

from pydantic import Field

from app.schemas.base import BaseResponse


class PriceTargetPoint(BaseResponse):
    """单月平均目标价."""

    label: str = Field(description="月份标签，如 2024-06")
    avg_target: float
    count: int


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
    # 近 18 个月月度目标价，用于表格 sparkline（与弹窗数据同源）
    recent_points: list[PriceTargetPoint] = Field(default_factory=list)


class Nasdaq100UpgradesResponse(BaseResponse):
    """纳斯达克 100 上调筛选结果."""

    as_of: str
    total_constituents: int
    upgrade_count: int
    stocks: list[UpgradeStock]


class SP500UpgradesResponse(BaseResponse):
    """标普 500 上调筛选结果."""

    as_of: str
    total_constituents: int
    upgrade_count: int
    stocks: list[UpgradeStock]


class PriceTargetHistoryResponse(BaseResponse):
    """个股历史目标价月度序列."""

    symbol: str
    points: list[PriceTargetPoint]
