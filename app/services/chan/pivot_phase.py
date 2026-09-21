"""缠论中枢生命周期状态机：把已有的中枢/笔/背驰结构翻译成「走到哪一步」的进度。

判定的核心难点——中枢延伸时会把「仍在中枢内反复」和「已突破但被延伸判定吞并」
的笔混在同一个 `pivot.elements` 里（见 pivot.py 的宽松重叠判据：只要有一点价格
重叠就吞并），因此不能靠 `len(post)` 判断是否已突破，必须复用
`_post_pivot_strokes` 之后，按 generate_buy2/3_signals 同一套「起点在中枢内、
终点越过边界」判据，在结果里找第一对突破笔+回踩笔。这里独立实现一份等价判据
（不改 signals.py，那是有随机模糊护栏的高风险模块，见设计文档）。

只描述「已经走到哪一步」的客观事实，不做涨跌预测——`leaving` 阶段给出的
`branches` 是规则本身在三种已定义结果下分别是什么（真值表），不是对未来的
主观判断。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.services.chan.i18n import pick
from app.services.chan.signals import _post_pivot_strokes

if TYPE_CHECKING:
    from app.services.chan.analyzer import ChanAnalysisResult
    from app.services.chan.pivot import Pivot
    from app.services.chan.stroke import Stroke

Phase = Literal[
    "pivot_forming", "pivot_oscillating", "leaving", "retrace_confirmed", "divergence_turn",
]
Outcome = Literal["type2", "type3", "back_to_range"]

_PHASE_ORDER: list[Phase] = [
    "pivot_forming", "pivot_oscillating", "leaving", "retrace_confirmed", "divergence_turn",
]

_NEXT_STEP: dict[Phase, tuple[str, str]] = {
    "pivot_forming": ("等待中枢是否延伸或被突破", "Waiting to see if the pivot extends or breaks"),
    "pivot_oscillating": ("等待突破中枢确认离开段", "Waiting for a breakout to confirm the leaving leg"),
    "leaving": ("等待离开段走完后回抽确认", "Waiting for the retrace to confirm after leaving"),
    "retrace_confirmed": ("关注后续走势是否出现背驰", "Watch for divergence as the move continues"),
}


@dataclass
class PhaseChecklistItem:
    label: str
    detail: str
    state: Literal["done", "pending"]


@dataclass
class PhaseBranch:
    outcome: Outcome
    condition_label: str
    result_label: str


@dataclass
class StageGuideStep:
    key: Phase
    title: str
    detail: str


@dataclass
class StageGuide:
    current_index: int
    steps: list[StageGuideStep] = field(default_factory=list)
    why_it_matters: str = ""


@dataclass
class PivotPhase:
    phase: Phase
    phase_label: str
    direction: Literal["up", "down"] | None
    pivot: "Pivot"
    checklist: list[PhaseChecklistItem] = field(default_factory=list)
    reason: str = ""
    confirmed: bool = True
    branches: list[PhaseBranch] = field(default_factory=list)
    stage_guide: StageGuide | None = None


@dataclass
class _Pair:
    """post 序列里第一对满足突破条件的（突破笔, 回踩笔）。"""
    breakout: "Stroke"
    retrace: "Stroke"
    direction: Literal["up", "down"]
    outcome: Outcome
    index: int  # breakout 在 post 里的下标，供定位「配对之后」的笔


def _find_first_pair(post: list["Stroke"], pivot: "Pivot") -> _Pair | None:
    """在 post 里找第一对突破笔+回踩笔，判据与 generate_buy2/3_signals 完全一致。"""
    for i in range(len(post) - 1):
        breakout, retrace = post[i], post[i + 1]
        if breakout.direction == "up" and breakout.start_price <= pivot.zg < breakout.end_price:
            if retrace.direction != "down":
                continue
            if retrace.end_price > pivot.zg:
                outcome: Outcome = "type3"
            elif retrace.end_price >= pivot.zd:
                outcome = "type2"
            else:
                outcome = "back_to_range"
            return _Pair(breakout, retrace, "up", outcome, i)
        if breakout.direction == "down" and breakout.start_price >= pivot.zd > breakout.end_price:
            if retrace.direction != "up":
                continue
            if retrace.end_price < pivot.zd:
                outcome = "type3"
            elif retrace.end_price <= pivot.zg:
                outcome = "type2"
            else:
                outcome = "back_to_range"
            return _Pair(breakout, retrace, "down", outcome, i)
    return None


def _find_open_breakout(post: list["Stroke"], pivot: "Pivot") -> "Stroke | None":
    """在 post 里找还没等到回抽笔、独自满足突破条件的最后一笔（leaving 阶段）。"""
    if not post:
        return None
    last = post[-1]
    if last.direction == "up" and last.start_price <= pivot.zg < last.end_price:
        return last
    if last.direction == "down" and last.start_price >= pivot.zd > last.end_price:
        return last
    return None


def _find_divergence_turn(
    result: "ChanAnalysisResult", remaining: list["Stroke"], direction: str,
) -> "Stroke | None":
    if not remaining:
        return None
    remaining_ids = {id(s) for s in remaining}
    for st, dv in zip(result.strokes, result.divergences, strict=False):
        if id(st) in remaining_ids and dv.is_diverged and st.direction == direction:
            return st
    return None


def _pick_current_pivot(result: "ChanAnalysisResult") -> tuple["Pivot", list["Pivot"], int] | None:
    """取 end_time 最新的中枢；并列时取线段级。返回 (中枢, 合并排序后的中枢表, 下标)。"""
    all_pivots = sorted([*result.stroke_pivots, *result.segment_pivots], key=lambda p: p.start_time)
    if not all_pivots:
        return None
    pivot = max(all_pivots, key=lambda p: (p.end_time, p.level == "segment"))
    return pivot, all_pivots, all_pivots.index(pivot)


def _phase_label(phase: Phase, direction: str | None, outcome: Outcome | None, lang: str) -> str:
    up = direction == "up"
    if phase == "pivot_forming":
        return pick(lang, "形成中枢", "Pivot formed")
    if phase == "pivot_oscillating":
        return pick(lang, "中枢震荡", "Pivot oscillating")
    if phase == "leaving":
        return pick(lang, "向上离开中枢" if up else "向下离开中枢",
                     "Leaving pivot upward" if up else "Leaving pivot downward")
    if phase == "retrace_confirmed":
        if outcome == "type3":
            return pick(lang, "确认三买" if up else "确认三卖",
                         "Type-3 buy confirmed" if up else "Type-3 sell confirmed")
        return pick(lang, "确认二买" if up else "确认二卖",
                     "Type-2 buy confirmed" if up else "Type-2 sell confirmed")
    return pick(lang, "顶背驰，趋势可能转折" if up else "底背驰，趋势可能转折",
                 "Top divergence, trend may turn" if up else "Bottom divergence, trend may turn")


def _next_step_label(phase: Phase, lang: str) -> str | None:
    entry = _NEXT_STEP.get(phase)
    if entry is None:
        return None
    zh, en = entry
    return pick(lang, zh, en)


def _checklist(phase: Phase, phase_label: str, detail: str, pivot: "Pivot", lang: str) -> list[PhaseChecklistItem]:
    items = [
        PhaseChecklistItem(label=pick(lang, "形成中枢", "Pivot formed"),
                            detail=f"{pivot.zd:.2f}–{pivot.zg:.2f}", state="done"),
    ]
    if phase != "pivot_forming":
        items.append(PhaseChecklistItem(label=phase_label, detail=detail, state="done"))
    next_label = _next_step_label(phase, lang)
    if next_label is not None:
        items.append(PhaseChecklistItem(label=next_label, detail="", state="pending"))
    return items


def _reason(phase: Phase, direction: str | None, pivot: "Pivot", last_price: float,
            pair: "_Pair | None", lang: str) -> str:
    up = direction == "up"
    if phase == "pivot_forming":
        return pick(lang,
            f"最近三段走势在 {pivot.zd:.2f}–{pivot.zg:.2f} 区间内重叠，刚形成中枢。",
            f"The last three legs overlapped within {pivot.zd:.2f}-{pivot.zg:.2f}, forming a pivot.")
    if phase == "pivot_oscillating":
        return pick(lang,
            f"价格持续在中枢 {pivot.zd:.2f}–{pivot.zg:.2f} 区间内反复，尚未离开。",
            f"Price keeps oscillating inside the pivot {pivot.zd:.2f}-{pivot.zg:.2f}, hasn't left yet.")
    if phase == "leaving":
        if up:
            return pick(lang,
                f"现价 {last_price:.2f} 已站上 ZG {pivot.zg:.2f}，最新向上笔离开了中枢区间。",
                f"Price {last_price:.2f} has cleared ZG {pivot.zg:.2f}; the latest up-leg left the pivot.")
        return pick(lang,
            f"现价 {last_price:.2f} 已跌破 ZD {pivot.zd:.2f}，最新向下笔离开了中枢区间。",
            f"Price {last_price:.2f} has broken below ZD {pivot.zd:.2f}; the latest down-leg left the pivot.")
    assert pair is not None
    if phase == "retrace_confirmed":
        if pair.outcome == "type3":
            boundary = pivot.zg if up else pivot.zd
            return pick(lang,
                f"回踩至 {pair.retrace.end_price:.2f}，守住 {'ZG' if up else 'ZD'} {boundary:.2f} 未回中枢，"
                f"确认{'三买' if up else '三卖'}。",
                f"Retrace held at {pair.retrace.end_price:.2f}, staying beyond "
                f"{'ZG' if up else 'ZD'} {boundary:.2f} — type-3 {'buy' if up else 'sell'} confirmed.")
        return pick(lang,
            f"回踩至 {pair.retrace.end_price:.2f}，落在中枢 {pivot.zd:.2f}–{pivot.zg:.2f} 内未破对侧边界，"
            f"确认{'二买' if up else '二卖'}。",
            f"Retrace landed at {pair.retrace.end_price:.2f}, inside the pivot "
            f"{pivot.zd:.2f}-{pivot.zg:.2f} — type-2 {'buy' if up else 'sell'} confirmed.")
    return pick(lang,
        f"延续的{'上升' if up else '下降'}笔出现{'顶' if up else '底'}背驰，动能未能同步创新高/新低。",
        f"The continuing {'up' if up else 'down'}-leg shows a {'top' if up else 'bottom'} divergence "
        "— momentum failed to confirm.")


def _branches(direction: str, pivot: "Pivot", lang: str) -> list[PhaseBranch]:
    up = direction == "up"
    near = pivot.zg if up else pivot.zd   # 突破跨越的边界
    far = pivot.zd if up else pivot.zg    # 对侧边界（回抽/反抽要守住或跌穿的边界）
    near_label = "ZG" if up else "ZD"
    far_label = "ZD" if up else "ZG"
    verb_zh = "回踩" if up else "反抽"
    verb_en = "Retrace" if up else "Bounce"
    side_zh = "以上" if up else "以下"
    buy_or_sell = "买" if up else "卖"
    buy_or_sell_en = "buy" if up else "sell"
    return [
        PhaseBranch("type3",
            pick(lang, f"{verb_zh}守住 {near_label} {near:.2f} {side_zh}，不回中枢",
                 f"{verb_en} holds beyond {near_label} {near:.2f}"),
            pick(lang, f"确认三{buy_or_sell}（趋势确认，最强）", f"Type-3 {buy_or_sell_en} confirmed (strongest)")),
        PhaseBranch("type2",
            pick(lang, f"{verb_zh}落在中枢区间内，未破 {far_label} {far:.2f}",
                 f"{verb_en} lands inside the pivot, holding {far_label} {far:.2f}"),
            pick(lang, f"确认二{buy_or_sell}（中枢升级，弱于三{buy_or_sell}）",
                 f"Type-2 {buy_or_sell_en} confirmed (weaker than type-3)")),
        PhaseBranch("back_to_range",
            pick(lang, f"{verb_zh}穿破 {far_label} {far:.2f}，重新进入中枢",
                 f"{verb_en} breaks through {far_label} {far:.2f}"),
            pick(lang, "假突破，回到中枢震荡", "False breakout — back to pivot oscillation")),
    ]


def _stage_guide(current_phase: Phase, direction: str | None, pivot: "Pivot", lang: str) -> StageGuide:
    # 方向未知（forming/oscillating 阶段）时讲解文案默认按「向上」措辞——只影响
    # 教学文案的措辞方向，不影响任何判定逻辑。
    up = direction != "down"
    steps = [
        StageGuideStep("pivot_forming", pick(lang, "中枢形成", "Pivot forms"),
                        pick(lang, f"三段重叠围出 {pivot.zd:.2f}–{pivot.zg:.2f}",
                             f"Three overlapping legs define {pivot.zd:.2f}-{pivot.zg:.2f}")),
        StageGuideStep("pivot_oscillating", pick(lang, "中枢震荡", "Pivot oscillates"),
                        pick(lang, "区间内反复，中枢延伸", "Price churns inside the range, pivot extends")),
        StageGuideStep("leaving", pick(lang, "离开段", "Leaving leg"),
                        pick(lang, f"{'向上' if up else '向下'}离开中枢，候选第三类{'买' if up else '卖'}点",
                             f"Leaving the pivot {'upward' if up else 'downward'}, "
                             f"a type-3 {'buy' if up else 'sell'} candidate")),
        StageGuideStep("retrace_confirmed", pick(lang, "回抽确认", "Retrace confirmation"),
                        pick(lang, f"回抽不进中枢 → 确认三{'买' if up else '卖'}",
                             f"Retrace stays out → type-3 {'buy' if up else 'sell'} confirmed")),
        StageGuideStep("divergence_turn", pick(lang, "背驰/转折", "Divergence / turn"),
                        pick(lang, "趋势末端背驰 → 一类买卖点", "End-of-trend divergence → type-1 signal")),
    ]
    return StageGuide(current_index=_PHASE_ORDER.index(current_phase), steps=steps,
                       why_it_matters=_why_it_matters(current_phase, up, lang))


def _why_it_matters(phase: Phase, up: bool, lang: str) -> str:
    zh = {
        "pivot_forming": "中枢一旦形成，后续所有笔的力度、回踩都以它的 ZG/ZD 为基准衡量。",
        "pivot_oscillating": "中枢延伸得越久，之后一旦突破，力度往往越强——这是蓄势阶段。",
        "leaving": ("离开段是缠论趋势能否延续的分水岭：" + ("向上" if up else "向下") +
                    "离开中枢后若回抽不进中枢，就确认三" + ("买" if up else "卖") +
                    "、中枢升级、趋势打开；若回抽跌回中枢，则回到震荡。"),
        "retrace_confirmed": "回抽确认之后，趋势能走多远就看后续同向的笔是否还有力度、会不会出现背驰。",
        "divergence_turn": "背驰意味着推动价格新高/新低的动能已经跟不上，是趋势可能见顶/见底的信号。",
    }
    en = {
        "pivot_forming": "Once a pivot forms, every later leg's strength and retrace are measured against its ZG/ZD.",
        "pivot_oscillating": "The longer a pivot extends, the stronger the eventual breakout tends to be.",
        "leaving": (f"The leaving leg is the fork in the road: after leaving {'upward' if up else 'downward'}, "
                    "if the retrace stays out of the pivot, it confirms a type-3 signal and the trend opens up; "
                    "if it falls back in, it returns to oscillation."),
        "retrace_confirmed": "How far the trend goes next depends on whether momentum holds or a divergence appears.",
        "divergence_turn": "Divergence means the momentum driving new highs/lows can't keep up — a common "
                            "precursor to a top or bottom.",
    }
    return pick(lang, zh[phase], en[phase])


def _build_oscillating(pivot: "Pivot", forming: bool, lang: str) -> PivotPhase:
    phase: Phase = "pivot_forming" if forming else "pivot_oscillating"
    label = _phase_label(phase, None, None, lang)
    reason = _reason(phase, None, pivot, 0.0, None, lang)
    return PivotPhase(phase=phase, phase_label=label, direction=None, pivot=pivot,
                       checklist=_checklist(phase, label, reason, pivot, lang), reason=reason,
                       confirmed=True, branches=[], stage_guide=_stage_guide(phase, None, pivot, lang))


def _build_leaving(pivot: "Pivot", breakout: "Stroke", last_price: float, lang: str) -> PivotPhase:
    direction = breakout.direction
    phase: Phase = "leaving"
    label = _phase_label(phase, direction, None, lang)
    reason = _reason(phase, direction, pivot, last_price, None, lang)
    return PivotPhase(phase=phase, phase_label=label, direction=direction, pivot=pivot,
                       checklist=_checklist(phase, label, reason, pivot, lang), reason=reason,
                       confirmed=breakout.confirmed, branches=_branches(direction, pivot, lang),
                       stage_guide=_stage_guide(phase, direction, pivot, lang))


def _build_retrace_confirmed(pivot: "Pivot", pair: _Pair, lang: str) -> PivotPhase:
    phase: Phase = "retrace_confirmed"
    label = _phase_label(phase, pair.direction, pair.outcome, lang)
    reason = _reason(phase, pair.direction, pivot, pair.retrace.end_price, pair, lang)
    return PivotPhase(phase=phase, phase_label=label, direction=pair.direction, pivot=pivot,
                       checklist=_checklist(phase, label, reason, pivot, lang), reason=reason,
                       confirmed=pair.retrace.confirmed, branches=[],
                       stage_guide=_stage_guide(phase, pair.direction, pivot, lang))


def _build_divergence_turn(pivot: "Pivot", pair: _Pair, turn_stroke: "Stroke", lang: str) -> PivotPhase:
    phase: Phase = "divergence_turn"
    label = _phase_label(phase, pair.direction, pair.outcome, lang)
    reason = _reason(phase, pair.direction, pivot, pair.retrace.end_price, pair, lang)
    return PivotPhase(phase=phase, phase_label=label, direction=pair.direction, pivot=pivot,
                       checklist=_checklist(phase, label, reason, pivot, lang), reason=reason,
                       confirmed=turn_stroke.confirmed, branches=[],
                       stage_guide=_stage_guide(phase, pair.direction, pivot, lang))


def build_pivot_phase(result: "ChanAnalysisResult", lang: str = "zh") -> PivotPhase | None:
    """构建「走到哪一步」状态。结构未成形（笔 < 3）或没有中枢时返回 None。"""
    if len(result.strokes) < 3:
        return None
    picked = _pick_current_pivot(result)
    if picked is None:
        return None
    pivot, all_pivots, idx = picked
    post = _post_pivot_strokes(result.strokes, all_pivots, idx)

    pair = _find_first_pair(post, pivot)
    if pair is None:
        open_breakout = _find_open_breakout(post, pivot)
        if open_breakout is not None:
            last_price = result.merged_candles[-1].close if result.merged_candles else 0.0
            return _build_leaving(pivot, open_breakout, last_price, lang)
        return _build_oscillating(pivot, forming=len(pivot.elements) <= 3, lang=lang)

    if pair.outcome == "back_to_range":
        return _build_oscillating(pivot, forming=False, lang=lang)

    remaining = post[pair.index + 2:]
    turn_stroke = _find_divergence_turn(result, remaining, pair.direction)
    if turn_stroke is not None:
        return _build_divergence_turn(pivot, pair, turn_stroke, lang)
    return _build_retrace_confirmed(pivot, pair, lang)
