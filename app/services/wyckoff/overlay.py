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

# 区间太窄（宽度不到支撑价的这个比例）视为没有识别出有效交易区间：真实数据里这类「区间」是几根 K 线的小波动，
# 画出来是一条细线加一堆事件，只会误导（RKLB 实测 22.01–22.55，宽度 2.4%）。
MIN_RANGE_WIDTH = 0.04
# 滚动识别的结构段数上限（两年日线里一般 1~3 段；封顶防止噪声里无限切分）。
MAX_STRUCTURES = 4
MAX_ROUNDS = 16
# 区间至少要有这么多根 K 线（合并 K 线下标之差）才画。
MIN_SPAN = 3
# 一段里认不出结构时，下一轮往后挪的 K 线数。
SCAN_STEP = 60
# 突破判定缓冲：与 phases.determine_phase 一致（区间宽度的 15%）。
_BREAK_BUF = 0.15


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
    ranges: list[OverlayRange] = field(default_factory=list)  # 按时间先后，最多 MAX_STRUCTURES 段
    events: list[OverlayEvent] = field(default_factory=list)


def _candle_index(end_times: list[str], t: str) -> int | None:
    """原始 K 线时间 → 它所在的合并 K 线下标（第一根 end_time ≥ t 的合并 K 线）。

    早于图上第一根（缠论会丢掉首笔确认前的前导 K 线）或晚于最后一根返回 None。
    """
    if not end_times or t < end_times[0]:
        return None
    i = bisect_left(end_times, t)
    return i if i < len(end_times) else None


def _breakout_time(bars: list[dict], start_time: str, support: float, resistance: float, width: float) -> str | None:
    """区间起点之后第一根收盘离开区间（超出 15% 区间宽度缓冲）的 K 线时间；一直在区间内返回 None。"""
    buf = width * _BREAK_BUF if width > 0 else resistance * 0.01
    for b in bars:
        t = str(b["time"])
        if t <= start_time:
            continue
        c = float(b["close"])
        if c > resistance + buf or c < support - buf:
            return t
    return None


def build_overlay(symbol: str, bars: list[dict], end_times: list[str], *, visible_from: str | None = None) -> WyckoffOverlay | None:
    """威科夫结构裁成图上叠加物。

    bars：含预热的原始 K 线（time/open/high/low/close/volume）；只用 `visible_from` 之后（含）的部分分析——
    威科夫看的是「当前这段」交易区间，不该被预热期更早的高潮抢走。
    end_times：缠论图合并 K 线各自的 `end_time or time`（升序），用来把事件对齐到下标。

    **滚动识别多段结构**：威科夫分析一次只认「量比最高的那个高潮」及其后的一段区间。价格离开区间后，从突破那根起
    再分析一遍，找下一段（下跌途中的卖出高潮 → 新的吸筹区间……），最多 MAX_STRUCTURES 段。
    只认一段时，视窗里大部分时间什么都没有（BABA 实测只剩 SC、AR 两个标记）。
    阶段取**最后一段**结构（= 当前所处阶段）。没有识别到结构仍返回对象（stage 为「结构不明」），数据不足 / 没有成交量返回 None。
    """
    if not end_times:
        return None
    use = [b for b in bars if visible_from is None or str(b["time"]) >= visible_from]
    if len(use) < 20 or not any((b.get("volume") or 0) > 0 for b in use):
        return None

    out = WyckoffOverlay(context="undetermined", stage="undetermined", stage_label="结构不明",
                         phase="", phase_label="", breakout="none")
    by_time = {str(b["time"]): b for b in use}
    last = len(end_times) - 1
    pos = 0  # 本轮分析从 use[pos:] 开始
    # 有效结构 ≤ MAX_STRUCTURES 段；被当作无效跳过的区间不占名额，但总轮数也封顶（防死循环 / 噪声里反复切）
    for _ in range(MAX_ROUNDS):
        if len(out.ranges) >= MAX_STRUCTURES:
            break
        seg = use[pos:]
        if len(seg) < 20:
            break
        r = _analyzer.analyze(symbol, seg)
        tr = r.trading_range
        if tr is None:
            # 这一段没有可用结构（分析只认量比最高的那个高潮，认不出来整段就是「结构不明」，
            # 但后面可能还有别的高潮，BABA 实测）：往后挪一截再试，直到走完
            pos += SCAN_STEP
            continue
        t_idx = next((k for k, b in enumerate(seg) if str(b["time"]) == tr.start_time), 0)
        if tr.support <= 0 or tr.width / tr.support < MIN_RANGE_WIDTH:
            # 这一段区间无效：跳过它的起点继续往后找，不把它当结构
            pos += max(1, t_idx + 1)
            continue

        # 区间画到突破那根为止（价格已离开区间后，区间不再描述当前，带子拉到今天会把整段行情罩住）；
        # 事件也只留到突破为止——之后重复出现的 SOS / SOW 是趋势里的放量，不是区间里的结构（NVDA 实测 11 个 SOS），
        # 突破之后的走势交给下一轮识别。
        cut = _breakout_time(seg, tr.start_time, tr.support, tr.resistance, tr.width)
        # 区间起点早于图上第一根就从最左边画起；突破点早于图上第一根说明整段区间都在图外，不画；
        # 短到不足 MIN_SPAN 根的不算区间（一两根 K 线的「区间」画出来是一条竖线）
        start = _candle_index(end_times, tr.start_time)
        if start is None and tr.start_time < end_times[0]:
            start = 0
        end_idx = last if cut is None else _candle_index(end_times, cut)
        if start is not None and end_idx is not None and end_idx - start >= MIN_SPAN:
            out.ranges.append(OverlayRange(kind=tr.kind, support=tr.support, resistance=tr.resistance,
                                           start_idx=start, end_idx=end_idx))
            for e in r.events:
                if cut is not None and e.time > cut:
                    continue
                idx = _candle_index(end_times, e.time)
                if idx is None:
                    continue
                bar = by_time.get(e.time)
                mid = (float(bar["high"]) + float(bar["low"])) / 2 if bar else e.price
                out.events.append(OverlayEvent(
                    code=e.code, name=e.name, idx=idx, time=e.time, price=e.price,
                    side="high" if e.price >= mid else "low", phase=e.phase, volume_ratio=e.volume_ratio,
                ))
            # 当前阶段 = 最后一段结构的阶段（只有最后一段的末价才是今天的价格）
            out.context = r.context
            if r.phase:
                out.stage, out.stage_label = r.phase.stage, r.phase.stage_label
                out.phase, out.phase_label, out.breakout = r.phase.phase, r.phase.phase_label, r.phase.breakout
        if cut is None:
            break
        nxt = next((k for k, b in enumerate(seg) if str(b["time"]) >= cut), None)
        if nxt is None:
            break
        pos += max(1, nxt)
    if not out.ranges:
        # 一段有效结构都没有：阶段也不保留（阶段是由区间推出来的）
        return WyckoffOverlay(context="undetermined", stage="undetermined", stage_label="结构不明",
                              phase="", phase_label="", breakout="none")
    return out
