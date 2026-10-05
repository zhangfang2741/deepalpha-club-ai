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
    # 形态技术面强度（0~1）：由信号自身的 strong/medium/weak 标签折算，旧版 App 截取前 N 时
    # 参与排序（display_rank）；新版 App 只按出现时间排。气泡大小由买卖点级别（一/二/三类）决定，
    # 颜色深浅由 signal_strength 决定（越强越深，与详情页买卖点「强/中/弱」一致）。
    strength: float = Field(description="形态技术面强度 0~1，决定看板淘汰排序")
    bias: str = Field(description="技术面倾向：bullish / bearish / neutral")
    signal_strength: str = Field(description="买卖点自身强度：strong / medium / weak，决定气泡颜色深浅")
    confirmed: bool = Field(description="信号是否已确认（未确认为右侧预判）")
    # 该信号发生当天的中枢生命周期阶段折算：形成中枢=浅/中枢震荡=中/已离开中枢
    # （离开段/回抽确认/背驰转折）=深，见 app/services/chan/replay.py 按发生
    # 日期回溯的 pivot_phase_as_of。旧版 App 用它决定气泡深浅，新版改按 signal_strength，保留兼容。
    pivot_stage_depth: float = Field(description="信号发生当天的中枢阶段深浅 0~1（旧版 App 的气泡深浅）")
    # 次级别确认（日线定方向 × 30 分钟找买卖点），只对最新交易日的部分信号补算（见 service.sub_level_targets）；
    # 其余日期、补算失败或 30 分钟不可用时为 None。见 app/services/chan/sub_level.py。
    sub_level_verdict: str | None = Field(
        default=None,
        description="resonance_buy / resonance_sell / counter_trend / waiting / unavailable",
    )
    sub_level_label: str | None = Field(default=None, description="次级别结论文案，如 共振买点")
    # 距所在展示日隔了几个交易日（周末、休市不算）。旧缓存里没有时为 None，客户端退回按自然日算。
    quant_grade: str | None = None
    quant_score: float | None = None
    quant_as_of: str | None = None
    quant_status: str | None = Field(default=None, description="eligible / below_threshold / missing / stale")
    age_days: int | None = Field(default=None, description="距展示日的交易日数，当天为 0")
    sector: str | None = Field(default=None, description="行业 key：美股与 regime 行业一致（GICS 一级），A 股为申万一级行业名，港股为恒生一级行业名；没有行业分类时为空")


class RadarExcludedOut(BaseModel):
    """基本面排雷排除的一条信号（2026-10-01 起不再排雷，恒为空，仅为旧版 App 兼容保留）。"""

    symbol: str
    name: str
    side: str = Field(description="buy / sell")
    signal_type: str
    rule: str = Field(description="profitability_f / revisions_f（买点）/ revisions_a_plus（卖点）")


class RadarQuantFilterOut(BaseModel):
    """统计覆盖所选股票池，数量不是气泡数。

    mode=marked：评级只展示（2026-10-01 起恒为 marked，不再排雷）。
    """

    mode: str = "marked"
    weight: float = 0.0
    min_grade: str | None = None
    status: str = "ready"
    eligible: int = 0
    below_threshold: int = 0
    missing: int = 0
    stale: int = 0
    max_age_days: int = 7
    preserve_sells: bool = False
    excluded: list[RadarExcludedOut] = Field(default_factory=list, description="已不再排雷，恒为空（旧版 App 兼容）")


class RadarDayOut(BaseModel):
    """某一交易日在场的信号快照。"""

    quant_filter: RadarQuantFilterOut | None = None
    date: str = Field(description="交易日 YYYY-MM-DD")
    buy_count: int = Field(description="当日买点数量")
    sell_count: int = Field(description="当日卖点数量")
    signals: list[RadarSignalOut] = Field(
        default_factory=list,
        description="当日在场的全部信号，按出现日期从新到旧（scope=all）；旧版 App（scope=top）为按旧综合分截取的前 N。"
                    "宽松口径下最后一笔上的信号也在这里，confirmed=false",
    )
    candidates: list[RadarSignalOut] = Field(
        default_factory=list,
        description="待确认候选（仅严格口径产出；宽松口径恒为空）：落在还没走完的最后一笔上，不算买卖点；"
                    "只在最新一天、补足剩余名额",
    )
    sector_counts: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="当天全部在场信号按行业的买卖点数 {行业: {buy, sell}}；没有行业分类时为空",
    )


class RadarSectorDayOut(BaseModel):
    """按行业筛选后的某一天气泡（GET /signal-radar/sector-day）。"""

    market: str
    universe: str
    date: str
    sector: str
    available: bool = Field(description="这一天是否有行业数据（旧快照、没有行业分类的市场为 false）")
    buy_count: int = 0
    sell_count: int = 0
    signals: list[RadarSignalOut] = Field(default_factory=list)


class RadarSectorPoolsOut(BaseModel):
    """某一天全部行业的气泡（GET /signal-radar/sector-pools）：App 一次取回，切行业不用再请求。"""

    market: str
    universe: str
    date: str
    available: bool = Field(description="这一天是否有行业数据（旧快照、没有行业分类的市场为 false）")
    sectors: dict[str, list[RadarSignalOut]] = Field(
        default_factory=dict, description="{行业 key: 该行业前 N 个气泡}；当天没有信号的行业不出现")


class RadarUniverseOut(BaseModel):
    """一个可选的扫描 universe（供前端左上角切换器）。"""

    key: str = Field(description="universe 唯一键，如 nasdaq100 / sp500")
    name: str = Field(description="展示名，如 纳斯达克100 / 标普500")
    is_default: bool = Field(default=False, description="是否该市场默认 universe")


class SignalRadarResponse(BaseModel):
    """信号雷达响应：某 (市场, universe) 最近若干交易日的每日信号。"""

    market: str = Field(description="市场：us / cn / hk")
    universe: str = Field(default="", description="当前 universe 键，如 nasdaq100 / sp500")
    universes: list[RadarUniverseOut] = Field(
        default_factory=list, description="该市场可选的全部 universe（默认在前）"
    )
    etf_name: str = Field(description="当前 universe 展示名（标题用）")
    universe_size: int = Field(description="扫描的成分股数量")
    as_of: str = Field(description="数据生成时间 YYYY-MM-DD")
    top_n: int = Field(description="旧版 App 每日展示的信号条数上限（scope=all 时不截取）")
    days: list[RadarDayOut] = Field(default_factory=list, description="最近交易日，最新在前")
    status: str = Field(default="ready", description="ready / generating（首次扫描进行中）")
    sub_level_as_of: str = Field(
        default="", description="最新一天气泡次级别（共振）结论的更新时间，ISO8601 UTC；盘中每 30 分钟刷新"
    )
    # as_of 只是「代表哪个交易日」的日期，不是「什么时候算出来的」——同一天内不管
    # 几点刷新都长一个样，看不出这份快照有多新。computed_at 是这次全量扫描
    # （build_days 生成全部 days 快照那一刻）的真实时间戳，供前端提示用户「你看到
    # 的气泡是这个时间点算出来的，跟现在重新点进详情页实时算的结果可能不完全一样」
    # ——尤其是缠论笔在数据右端本身就是临时性的，晚几根K线就可能改写，这是预期行为
    # 不是 bug，只是需要让用户看得到「有多新」。
    computed_at: str = Field(
        default="", description="本次全量扫描完成时间，ISO8601 UTC；缓存命中时沿用缓存写入时的时间"
    )
    signal_mode: str = Field(default="loose", description="买卖点口径（见 GET /chan/signal-modes）")
    pending_symbols: int = Field(
        default=0, description="拉数失败、正在后台补算的成分股数；补齐后快照会自动重写（0=已全部算完）"
    )


class RadarGradeEventOut(BaseModel):
    """基本面研究 tab 的一条事件：某只股票在某天综合等级升 / 降。"""

    symbol: str
    name: str
    date: str = Field(description="新等级的评级日 YYYY-MM-DD")
    direction: str = Field(description="up = 升档 / down = 降档")
    from_grade: str
    to_grade: str
    steps: int = Field(description="变动档数（13 档字母等级，A+ 最高、F 最低）")
    sector: str | None = None
    score: float | None = Field(default=None, description="新等级的综合分 0~100")


class RadarGradeDayOut(BaseModel):
    date: str
    up_count: int
    down_count: int
    events: list[RadarGradeEventOut]


class RadarGradeEventsResponse(BaseModel):
    """某 (市场, universe) 最近若干评级日的综合等级升降事件（从新到旧）。"""

    market: str
    universe_key: str
    universe_name: str = ""
    days: list[RadarGradeDayOut] = Field(default_factory=list)
    available: bool = Field(default=True, description="False = 评级数据读取失败（不是没有事件）")
