"""分析师目标价上调 Pydantic schemas."""

from pydantic import Field

from app.schemas.base import BaseResponse


class PriceTargetPoint(BaseResponse):
    """单月平均目标价."""

    label: str = Field(description="月份标签，如 2024-06")
    avg_target: float
    count: int


class StockPricePoint(BaseResponse):
    """单月股价（月末收盘价）."""

    label: str = Field(description="月份标签，如 2024-06")
    close: float


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
    # 对应区间内的月度股价（月末收盘），用于图表叠加对比。为空表示未拉取股价。
    price_points: list[StockPricePoint] = Field(default_factory=list)


# ---------- 个股分析师评级概览（缠论 App 详情页「分析师评级」Tab） ----------


class RatingCounts(BaseResponse):
    """某月五档评级人数."""

    date: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    total: int


class RatingSection(BaseResponse):
    """评级分布：当前一月 + 月度趋势（旧 → 新）."""

    current: RatingCounts | None = None
    history: list[RatingCounts] = Field(default_factory=list)
    change_text: str | None = Field(None, description="近 3 个月买入及以上人数变化的中性描述")
    bucket_labels: list[str] | None = Field(
        default=None, description="五档名称（A 股 / 港股：买入 / 增持 / 中性 / 减持 / 卖出）；为空时用美股档位（强力买入 … 强力卖出）")


class PriceTargetSection(BaseResponse):
    """目标价（分析师一致目标价）与现价."""

    price: float | None = None
    high: float | None = None
    low: float | None = None
    median: float | None = None
    consensus: float | None = None
    vs_price_pct: float | None = Field(None, description="中位目标价相对现价的算术差（%）")
    vs_price_text: str | None = None
    last_month_count: int | None = None
    last_quarter_count: int | None = None
    last_year_count: int | None = None


class EarningsQuarter(BaseResponse):
    """一个已披露季度：实际 vs 预期 EPS."""

    date: str
    eps_actual: float
    eps_estimated: float | None = None
    surprise_pct: float | None = None


class NextEarnings(BaseResponse):
    """下次财报披露."""

    date: str
    eps_estimated: float | None = None
    revenue_estimated: float | None = None


class EarningsSection(BaseResponse):
    """业绩：近 4 季预期 vs 实际 + 下次披露."""

    quarters: list[EarningsQuarter] = Field(default_factory=list)
    next: NextEarnings | None = None


class GradeChange(BaseResponse):
    """一条机构评级变动（评级标签为分析师原文引述）."""

    date: str
    firm: str
    action: str
    action_label: str
    previous_grade: str | None = None
    previous_grade_label: str | None = None
    new_grade: str
    new_grade_label: str
    price_target: float | None = Field(default=None, description="本次给出的目标价（A 股人民币 / 港股港元）")
    report_title: str | None = Field(default=None, description="研报标题（仅 A 股有）")
    report_kind: str | None = Field(default=None, description="report = 研报原文 PDF（A 股）；news = 相关新闻报道（美股）")
    report_url: str | None = Field(default=None, description="研报原文 PDF 直链（仅 A 股有）")


class RelatedNews(BaseResponse):
    """与券商评级 / 目标价相关的媒体报道（港股：没有研报原文时的补充）."""

    date: str
    source: str | None = None
    title: str
    url: str


class AnalystOverviewOut(BaseResponse):
    """个股分析师评级概览."""

    symbol: str
    status: str = Field(description="ok | unsupported_market | insufficient_data")
    status_note: str | None = None
    ratings: RatingSection | None = None
    price_target: PriceTargetSection | None = None
    earnings: EarningsSection | None = None
    recent_grades: list[GradeChange] = Field(default_factory=list)
    related_news: list[RelatedNews] = Field(default_factory=list, description="评级相关报道（仅港股）")
    recent_grades_title: str | None = Field(default=None, description="评级列表标题（港股只有各券商最新评级时给出）")
    note: str
