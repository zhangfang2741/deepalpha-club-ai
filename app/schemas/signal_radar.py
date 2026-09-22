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
    # 形态技术面强度（0~1）：由信号自身的 strong/medium/weak 标签折算，决定看板
    # 满员时的淘汰排序（display_rank），不再决定气泡视觉——气泡大小由买卖点级别
    # （一/二/三类）决定，颜色深浅由 pivot_stage_depth 决定。
    strength: float = Field(description="形态技术面强度 0~1，决定看板淘汰排序")
    bias: str = Field(description="技术面倾向：bullish / bearish / neutral")
    signal_strength: str = Field(description="买卖点自身强度：strong / medium / weak")
    confirmed: bool = Field(description="信号是否已确认（未确认为右侧预判）")
    # 该信号发生当天的中枢生命周期阶段折算：形成中枢=浅/中枢震荡=中/已离开中枢
    # （离开段/回抽确认/背驰转折）=深，见 app/services/chan/replay.py 按发生
    # 日期回溯的 pivot_phase_as_of。决定前端气泡颜色深浅。
    pivot_stage_depth: float = Field(description="信号发生当天的中枢阶段深浅 0~1，决定气泡颜色深浅")


class RadarDayOut(BaseModel):
    """某一交易日的当日信号快照（前 N 只）。"""

    date: str = Field(description="交易日 YYYY-MM-DD")
    buy_count: int = Field(description="当日买点数量")
    sell_count: int = Field(description="当日卖点数量")
    signals: list[RadarSignalOut] = Field(default_factory=list, description="当日信号，按强度降序")


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
    top_n: int = Field(description="每日展示的信号条数上限")
    days: list[RadarDayOut] = Field(default_factory=list, description="最近交易日，最新在前")
    status: str = Field(default="ready", description="ready / generating（首次扫描进行中）")
