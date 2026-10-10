"""SMC「图表指标」：把结构识别结果裁成图上要画的东西，位置按缠论图的合并 K 线下标对齐。

和威科夫 / 均线 / BOLL 同一思路（见 `wyckoff/overlay.py`、`chan/ma.py`）：App 直接按下标画，不必再对时间。
只陈列位置与事实，**不带操作建议与买卖导向措辞**（`test_overlay_has_no_trading_wording` 守护）。

取舍（只画读得过来的）：
- 订单块、缺口只留**还没失效 / 没被填补**的，各取最近几个；失效的是历史、画出来只会铺满整张图；
- 结构突破只留可见窗口内发生的；订单块 / 缺口即使产生在窗口之前，只要还没失效就画（左端裁到最左一根）；
- 等高低点、流动性扫荡只留窗口内最近几个。
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from app.services.smc import algo

MAX_BREAKS = 14
MAX_ORDER_BLOCKS = 6
MAX_FVGS = 8
MAX_EQUAL_LEVELS = 6
MAX_SWEEPS = 8
MIN_BARS = 30


@dataclass
class BreakMark:
    """结构突破 / 转变标记。"""

    kind: str            # bos | choch
    direction: str       # bull | bear
    level: float
    level_idx: int       # 被突破的摆动点（左端裁到最左一根）
    break_idx: int
    time: str            # 突破那根的时间


@dataclass
class OrderBlockMark:
    """订单块标记。"""

    direction: str
    top: float
    bottom: float
    idx: int             # 区块那根 K 线（左端裁到最左一根）
    end_idx: int         # 没失效 = 最后一根
    mitigated: bool
    volume_ratio: float
    time: str


@dataclass
class FvgMark:
    """公允价值缺口标记。"""

    direction: str
    top: float
    bottom: float
    idx: int
    end_idx: int
    time: str


@dataclass
class EqualLevelMark:
    """等高 / 等低点标记。"""

    kind: str            # eqh | eql
    price: float
    idx1: int
    idx2: int


@dataclass
class SweepMark:
    """流动性扫荡标记。"""

    side: str            # high | low
    level: float
    level_idx: int
    idx: int
    time: str


@dataclass
class ZoneMark:
    """溢价 / 折价区。"""

    top: float
    bottom: float
    equilibrium: float
    start_idx: int
    end_idx: int


@dataclass
class ExtremeMark:
    """强 / 弱高低点之一。"""

    price: float
    idx: int
    strength: str        # strong | weak


@dataclass
class ExtremesMark:
    """一组强弱高低点。"""

    high: ExtremeMark
    low: ExtremeMark


@dataclass
class KeyLevelMark:
    """前周期高低点。"""

    code: str            # PDH / PDL / PWH / PWL / PMH / PML
    price: float
    start_idx: int


@dataclass
class SmcOverlay:
    """SMC 图表指标的全部内容。"""

    trend: str           # bull | bear | none
    swing_len: int
    breaks: list[BreakMark] = field(default_factory=list)
    order_blocks: list[OrderBlockMark] = field(default_factory=list)
    fvgs: list[FvgMark] = field(default_factory=list)
    equal_levels: list[EqualLevelMark] = field(default_factory=list)
    sweeps: list[SweepMark] = field(default_factory=list)
    zone: ZoneMark | None = None
    extremes: ExtremesMark | None = None
    key_levels: list[KeyLevelMark] = field(default_factory=list)


def _candle_index(end_times: list[str], t: str) -> int | None:
    """原始 K 线时间 → 它所在的合并 K 线下标（第一根 end_time ≥ t 的合并 K 线）；晚于最后一根返回 None。"""
    i = bisect_left(end_times, t)
    return i if i < len(end_times) else None


def build_overlay(bars: list[dict], end_times: list[str], freq: str, *,
                  swing_len: int | None = None, visible_from: str | None = None) -> SmcOverlay | None:
    """bars：含预热的原始 K 线；结构在完整序列上识别（预热决定早期摆动点），再只留可见窗口要画的。

    end_times：缠论图合并 K 线各自的 `end_time or time`（升序）。K 线太少返回 None。
    """
    if not end_times or len(bars) < MIN_BARS:
        return None
    res = algo.analyze(bars, swing_len=swing_len, freq=freq)
    first, last = end_times[0], len(end_times) - 1
    vf = visible_from or first
    times = [str(b["time"]) for b in bars]

    def at(idx: int) -> int | None:
        """事件所在合并 K 线下标；在图左边之外返回 None。"""
        if times[idx] < first:
            return None
        return _candle_index(end_times, times[idx])

    def left(idx: int) -> int:
        """起点在图左边之外时裁到最左一根。"""
        return at(idx) or 0

    out = SmcOverlay(trend=res.trend, swing_len=res.swing_len)

    for b in res.breaks:
        if times[b.break_idx] < vf or (bi := at(b.break_idx)) is None:
            continue
        out.breaks.append(BreakMark(b.kind, b.direction, b.level, left(b.level_idx), bi, times[b.break_idx]))
    out.breaks = out.breaks[-MAX_BREAKS:]

    obs = [o for o in res.order_blocks if o.mitigated_idx is None]
    for o in obs[-MAX_ORDER_BLOCKS:]:
        out.order_blocks.append(OrderBlockMark(o.direction, o.top, o.bottom, left(o.idx), last, False,
                                               o.volume_ratio, times[o.idx]))

    for g in [g for g in res.fvgs if g.filled_idx is None][-MAX_FVGS:]:
        out.fvgs.append(FvgMark(g.direction, g.top, g.bottom, left(g.idx), last, times[g.idx]))

    for e in res.equal_levels:
        if times[e.idx2] >= vf and at(e.idx2) is not None:
            out.equal_levels.append(EqualLevelMark(e.kind, e.price, left(e.idx1), left(e.idx2)))
    out.equal_levels = out.equal_levels[-MAX_EQUAL_LEVELS:]

    for s in res.sweeps:
        if times[s.idx] >= vf and (si := at(s.idx)) is not None:
            out.sweeps.append(SweepMark(s.side, s.level, left(s.level_idx), si, times[s.idx]))
    out.sweeps = out.sweeps[-MAX_SWEEPS:]

    if res.zone:
        z = res.zone
        out.zone = ZoneMark(z.top, z.bottom, z.equilibrium, left(z.start_idx), last)
    if res.extremes:
        x = res.extremes
        out.extremes = ExtremesMark(ExtremeMark(x.high.price, left(x.high.idx), x.high.strength),
                                    ExtremeMark(x.low.price, left(x.low.idx), x.low.strength))
    out.key_levels = [KeyLevelMark(k.code, k.price, left(k.start_idx)) for k in res.key_levels]
    return out
