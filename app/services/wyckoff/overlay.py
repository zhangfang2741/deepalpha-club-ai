"""威科夫「图表指标」：把威科夫分析结果裁成图上要画的东西（交易区间 + 事件标记 + 阶段标签）。

与 `/wyckoff/analysis`（网页端完整报告）的区别：这里只陈列图上看得见的结构事实，
**不带操作建议与「买点 / 离场点」措辞**（App 只陈列事实、不引导操作）；位置按缠论图的合并 K 线下标对齐，
App 直接按下标画，不必再对时间（与均线 / BOLL 同一思路，见 `chan/ma.py`）。
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from app.services.wyckoff.analyzer import WyckoffAnalyzer

_analyzer = WyckoffAnalyzer()


@dataclass
class OverlayEvent:
    code: str            # SC / AR / ST / SPRING / SOS / UT / UTAD / SOW / LPS / LPSY / PS / PSY / BC / TEST / BU
    name: str            # 中文名
    idx: int             # 合并 K 线下标
    time: str
    price: float
    side: str            # "high"：标在 K 线上方 / "low"：标在下方（按该 K 线上事件价更靠近高点还是低点）
    phase: str           # A / B / C / D / E
    volume_ratio: float  # 相对均量倍数


@dataclass
class OverlayRange:
    kind: str            # accumulation / distribution
    support: float
    resistance: float
    start_idx: int
    end_idx: int         # 区间画到的最后一根（区间还没被突破时就是最后一根 K 线）


@dataclass
class WyckoffOverlay:
    context: str                       # accumulation / distribution / undetermined
    stage: str                         # accumulation / markup / distribution / markdown / undetermined
    stage_label: str
    phase: str                         # A–E，没有则空
    phase_label: str
    breakout: str                      # up / down / none
    trading_range: OverlayRange | None = None
    events: list[OverlayEvent] = field(default_factory=list)


def _candle_index(end_times: list[str], t: str) -> int | None:
    """原始 K 线时间 → 它所在的合并 K 线下标（第一根 end_time ≥ t 的合并 K 线）；落在整段之后返回 None。"""
    i = bisect_left(end_times, t)
    return i if i < len(end_times) else None


def build_overlay(symbol: str, bars: list[dict], end_times: list[str], *, visible_from: str | None = None) -> WyckoffOverlay | None:
    """威科夫结构裁成图上叠加物。

    bars：含预热的原始 K 线（time/open/high/low/close/volume）；只用 `visible_from` 之后（含）的部分分析——
    威科夫看的是「当前这段」交易区间，不该被预热期更早的高潮抢走。
    end_times：缠论图合并 K 线各自的 `end_time or time`（升序），用来把事件对齐到下标。
    没有识别到结构（context=undetermined）仍返回对象（stage 为「结构不明」），数据不足 / 没有成交量返回 None。
    """
    if not end_times:
        return None
    use = [b for b in bars if visible_from is None or str(b["time"]) >= visible_from]
    if len(use) < 20 or not any((b.get("volume") or 0) > 0 for b in use):
        return None

    r = _analyzer.analyze(symbol, use)
    stage = r.phase
    out = WyckoffOverlay(
        context=r.context,
        stage=stage.stage if stage else "undetermined",
        stage_label=stage.stage_label if stage else "结构不明",
        phase=stage.phase if stage else "",
        phase_label=stage.phase_label if stage else "",
        breakout=stage.breakout if stage else "none",
    )
    if r.trading_range is None:
        return out

    by_time = {str(b["time"]): b for b in use}
    tr = r.trading_range
    start = _candle_index(end_times, tr.start_time)
    if start is not None:
        out.trading_range = OverlayRange(
            kind=tr.kind, support=tr.support, resistance=tr.resistance,
            start_idx=start, end_idx=len(end_times) - 1,
        )
    for e in r.events:
        idx = _candle_index(end_times, e.time)
        if idx is None:
            continue
        bar = by_time.get(e.time)
        mid = (float(bar["high"]) + float(bar["low"])) / 2 if bar else e.price
        out.events.append(OverlayEvent(
            code=e.code, name=e.name, idx=idx, time=e.time, price=e.price,
            side="high" if e.price >= mid else "low", phase=e.phase, volume_ratio=e.volume_ratio,
        ))
    return out
