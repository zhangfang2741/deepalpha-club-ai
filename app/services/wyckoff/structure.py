"""交易区间与威科夫事件识别。

流程：
1. 以「量能高潮」摆动点定位吸筹 / 派发的起点（SC 卖出高潮 / BC 买入高潮）；
2. 由高潮点划定交易区间（trading range）的支撑 / 阻力；
3. 沿区间向后识别 AR、ST、Spring、SOS、UT、UTAD、SOW、LPS/LPSY 等事件。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.wyckoff.indicators import Swing, VolumeStats


# 威科夫事件中文名与释义
EVENT_META: dict[str, tuple[str, str]] = {
    "PS": ("初步支撑", "下跌中首次放量承接，暗示卖压开始被吸收"),
    "SC": ("卖出高潮", "恐慌抛售、极端放量与宽幅下跌，往往形成交易区间的低点"),
    "AR": ("自动反弹", "卖压枯竭后的反弹，其高点界定交易区间上沿（吸筹）"),
    "ST": ("二次测试", "回踩 SC 低点区域，缩量表明卖压减轻"),
    "SPRING": ("弹簧/震仓", "短暂跌破支撑后迅速收回的诱空，是理想的吸筹买点"),
    "TEST": ("测试", "对弹簧低点的低量回踩，确认下方无供给"),
    "SOS": ("强势信号", "放量宽幅上涨并逼近/突破区间上沿，需求主导"),
    "LPS": ("最后支撑点", "SOS 后的回踩不再创新低，是拉升前的介入点"),
    "BU": ("回踩确认", "突破区间后回抽上沿获得支撑（Back Up）"),
    "PSY": ("初步供给", "上涨中首次放量遇阻，暗示买压开始被消化"),
    "BC": ("买入高潮", "追涨放量与宽幅上冲，往往形成交易区间的高点"),
    "UT": ("冲高回落", "短暂突破阻力后迅速回落的诱多"),
    "UTAD": ("派发后冲高", "派发末端的诱多突破，是理想的做空/离场点"),
    "SOW": ("弱势信号", "放量宽幅下跌并跌破区间下沿，供给主导"),
    "LPSY": ("最后供给点", "SOW 后的反弹无力、不再创新高，是下跌前的离场点"),
}


@dataclass
class WyckoffEvent:
    code: str
    name: str
    idx: int
    time: str
    price: float
    volume_ratio: float   # 相对均量倍数
    phase: str            # A / B / C / D / E
    description: str


@dataclass
class TradingRange:
    kind: str             # "accumulation" | "distribution"
    support: float
    resistance: float
    start_idx: int
    start_time: str
    end_idx: int
    end_time: str

    @property
    def width(self) -> float:
        """交易区间宽度（阻力 − 支撑）。"""
        return max(self.resistance - self.support, 0.0)


@dataclass
class StructureResult:
    context: str                    # "accumulation" | "distribution" | "undetermined"
    trading_range: TradingRange | None = None
    events: list[WyckoffEvent] = field(default_factory=list)
    climax_swing: Swing | None = None


def _volume_ratio(vstats: VolumeStats, idx: int) -> float:
    return round(vstats.ratio(idx), 2)


def detect_structure(
    bars: list[dict],
    swings: list[Swing],
    vstats: VolumeStats,
    *,
    climax_vol_ratio: float = 1.6,
    st_tol: float = 0.04,
    trend_min: float = 0.12,
) -> StructureResult:
    """识别交易区间及威科夫事件序列。

    climax_vol_ratio：判定量能高潮所需的最小放量倍数。
    st_tol：ST / Spring 判定的价格容差（相对区间宽度或价格的比例）。
    trend_min：高潮前所需的最小趋势幅度（威科夫核心前提：SC 前必有显著下跌、
        BC 前必有显著上涨），达不到则视为无清晰吸筹/派发结构。
    """
    if len(swings) < 3:
        return StructureResult(context="undetermined")

    # 1. 定位量能高潮摆动点。威科夫方法论要求高潮出现在一段显著趋势之后，
    #    且随后出现反向反弹（AR），否则不构成吸筹/派发结构。
    climax = _find_climax(bars, swings, vstats, climax_vol_ratio, trend_min)
    if climax is None:
        return StructureResult(context="undetermined")

    if climax.kind == "low":
        result = _build_accumulation(bars, swings, vstats, climax, st_tol)
    else:
        result = _build_distribution(bars, swings, vstats, climax, st_tol)

    # 交易区间宽度必须为正，否则不认为存在有效区间
    if result.trading_range is not None and result.trading_range.width <= 0:
        return StructureResult(context="undetermined")
    return result


def _find_climax(
    bars: list[dict], swings: list[Swing], vstats: VolumeStats, min_ratio: float, trend_min: float,
) -> Swing | None:
    """在摆动点中选出真正的量能高潮点（SC / BC）。

    合格条件（缺一不可）：
    1. 放量达标：量比 >= min_ratio；
    2. 趋势前提：摆动低点前须有 >= trend_min 的下跌（SC），摆动高点前须有
       >= trend_min 的上涨（BC）——这是区分「高潮」与普通趋势中放量的关键；
    3. 极值确认：该点为此前价格的最低/最高（含微小容差）；
    4. 反向反弹：其后至少存在一个反向摆动点（对应 AR 自动反弹/回落）。

    在全部合格点中取量比最高者为最具代表性的高潮。若无合格点，返回 None
    （表示无清晰的吸筹/派发结构，而非强行判定）。
    """
    extreme_tol = 0.005
    valid: list[Swing] = []
    for s in swings:
        if vstats.ratio(s.idx) < min_ratio:
            continue
        # 其后需有反向摆动（AR）
        if not any(o.kind != s.kind for o in swings if o.idx > s.idx):
            continue
        if s.idx <= 0:
            continue
        if s.kind == "low":
            prior_high = max((b["high"] for b in bars[: s.idx]), default=s.price)
            decline = (prior_high - s.price) / s.price if s.price else 0.0
            lowest = min(b["low"] for b in bars[: s.idx + 1])
            is_extreme = s.price <= lowest * (1 + extreme_tol)
            if decline >= trend_min and is_extreme:
                valid.append(s)
        else:  # high
            prior_low = min((b["low"] for b in bars[: s.idx]), default=s.price)
            advance = (s.price - prior_low) / prior_low if prior_low else 0.0
            highest = max(b["high"] for b in bars[: s.idx + 1])
            is_extreme = s.price >= highest * (1 - extreme_tol)
            if advance >= trend_min and is_extreme:
                valid.append(s)

    if not valid:
        return None
    return max(valid, key=lambda s: vstats.ratio(s.idx))


def _mk_event(code: str, sw: Swing, vstats: VolumeStats, phase: str, extra: str = "") -> WyckoffEvent:
    name, brief = EVENT_META[code]
    desc = brief + (f"；{extra}" if extra else "")
    return WyckoffEvent(
        code=code, name=name, idx=sw.idx, time=sw.time, price=sw.price,
        volume_ratio=_volume_ratio(vstats, sw.idx), phase=phase, description=desc,
    )


def _build_accumulation(
    bars: list[dict], swings: list[Swing], vstats: VolumeStats, sc: Swing, st_tol: float,
) -> StructureResult:
    """以 SC（卖出高潮）为起点构建吸筹结构。"""
    events: list[WyckoffEvent] = []
    support = sc.price
    resistance = sc.price

    # PS：SC 之前最近一个放量的下降摆动低点
    ps = _find_preliminary(swings, vstats, sc, kind="low")
    if ps is not None:
        events.append(_mk_event("PS", ps, vstats, "A"))

    events.append(_mk_event("SC", sc, vstats, "A"))

    after = [s for s in swings if s.idx > sc.idx]
    tol = max(support * st_tol, 1e-9)

    # AR：SC 之后第一个摆动高点，界定阻力
    ar = next((s for s in after if s.kind == "high"), None)
    if ar is not None:
        resistance = ar.price
        events.append(_mk_event("AR", ar, vstats, "A"))

    # 逐个摆动点归类
    spring_done = False
    sos_done = False
    for s in after:
        if ar is not None and s.idx <= ar.idx:
            continue
        if s.kind == "low":
            if s.price < support - tol and not spring_done:
                # 跌破支撑后能收回 → Spring
                events.append(_mk_event("SPRING", s, vstats, "C",
                                        extra=f"跌破支撑 {support:.2f} 后收回"))
                spring_done = True
            elif abs(s.price - support) <= tol:
                events.append(_mk_event("ST", s, vstats, "B"))
            elif sos_done and s.price > support + tol:
                events.append(_mk_event("LPS", s, vstats, "D",
                                        extra="回踩不创新低，拉升前的支撑"))
            support = min(support, s.price)
        else:  # high
            if resistance and s.price >= resistance - tol and vstats.ratio(s.idx) >= 1.2:
                events.append(_mk_event("SOS", s, vstats, "D",
                                        extra=f"放量逼近/突破阻力 {resistance:.2f}"))
                sos_done = True
            resistance = max(resistance, s.price) if resistance else s.price

    tr = TradingRange(
        kind="accumulation", support=support, resistance=resistance or sc.price,
        start_idx=sc.idx, start_time=sc.time,
        end_idx=len(bars) - 1, end_time=bars[-1]["time"],
    )
    return StructureResult(context="accumulation", trading_range=tr, events=events, climax_swing=sc)


def _build_distribution(
    bars: list[dict], swings: list[Swing], vstats: VolumeStats, bc: Swing, st_tol: float,
) -> StructureResult:
    """以 BC（买入高潮）为起点构建派发结构。"""
    events: list[WyckoffEvent] = []
    resistance = bc.price
    support = bc.price

    psy = _find_preliminary(swings, vstats, bc, kind="high")
    if psy is not None:
        events.append(_mk_event("PSY", psy, vstats, "A"))

    events.append(_mk_event("BC", bc, vstats, "A"))

    after = [s for s in swings if s.idx > bc.idx]
    tol = max(resistance * st_tol, 1e-9)

    # AR：BC 之后第一个摆动低点，界定支撑
    ar = next((s for s in after if s.kind == "low"), None)
    if ar is not None:
        support = ar.price
        events.append(_mk_event("AR", ar, vstats, "A"))

    ut_done = False
    sow_done = False
    for s in after:
        if ar is not None and s.idx <= ar.idx:
            continue
        if s.kind == "high":
            if s.price > resistance + tol:
                code = "UTAD" if ut_done else "UT"
                events.append(_mk_event(code, s, vstats, "C",
                                        extra=f"突破阻力 {resistance:.2f} 后回落"))
                ut_done = True
            elif abs(s.price - resistance) <= tol:
                events.append(_mk_event("ST", s, vstats, "B"))
            elif sow_done and s.price < resistance - tol:
                events.append(_mk_event("LPSY", s, vstats, "D",
                                        extra="反弹不创新高，下跌前的供给点"))
            resistance = max(resistance, s.price)
        else:  # low
            if support and s.price <= support + tol and vstats.ratio(s.idx) >= 1.2:
                events.append(_mk_event("SOW", s, vstats, "D",
                                        extra=f"放量跌破支撑 {support:.2f}"))
                sow_done = True
            support = min(support, s.price) if support else s.price

    tr = TradingRange(
        kind="distribution", support=support or bc.price, resistance=resistance,
        start_idx=bc.idx, start_time=bc.time,
        end_idx=len(bars) - 1, end_time=bars[-1]["time"],
    )
    return StructureResult(context="distribution", trading_range=tr, events=events, climax_swing=bc)


def _find_preliminary(swings: list[Swing], vstats: VolumeStats, climax: Swing, kind: str) -> Swing | None:
    """在高潮点之前寻找同向的初步支撑/供给（放量的前一个同类摆动点）。"""
    before = [s for s in swings if s.idx < climax.idx and s.kind == kind]
    if not before:
        return None
    cand = before[-1]
    return cand if vstats.ratio(cand.idx) >= 1.2 else None
