# 缠论详情页「进度主线」（pivot_phase）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给缠论分析新增 `pivot_phase` 中枢生命周期状态机（后端），并在 iOS 详情页
的「整体分析」段落里加入「走到哪一步」进度条 + 阶段讲解弹层（iOS），承接设计文档
[2026-09-22-chan-pivot-phase-design.md](2026-09-22-chan-pivot-phase-design.md)。

**Architecture:** 后端新增独立模块 `app/services/chan/pivot_phase.py`，复用已有的
`stroke_pivots`/`segment_pivots`/`strokes`/`divergences` 结构，独立实现一份与
`signals.py` 里 `generate_buy2/3_signals` 等价的"找第一对突破笔+回踩笔"判据（不
改动 `signals.py`，见设计文档「与 signals.py 的关系」），归类出 6 种 phase，随
`ChanAnalysis` 一起下发。iOS 侧扩展 `ChanModels.swift`，在 `AnalysisSection`
渲染新区块，新增 `PivotPhaseGuideSheet` 承载阶段讲解弹层。

**Tech Stack:** Python 3.13 / dataclass / pytest（`asyncio_mode=auto`，本模块是同步代码不受影响）；Swift / SwiftUI（iOS 26 目标，仿现有 `CollapsibleCard`/`Chip`/`BulletList` 组件风格）

---

## 前置说明（写给执行这个计划的工程师）

- 后端测试目录 `tests/services/chan/` 大量采用「手搭 Stroke/Pivot/DivergenceResult
  对象直接测函数」的风格（见 `tests/services/chan/test_trend_outlook.py`），不
  跑完整的 K 线 → 分析全流程。本计划的新测试延续这个风格。
- **关键实现坑**（已在设计文档里记录，这里重复一遍避免执行时踩坑）：`pivot.py`
  的中枢延伸判定是"只要笔与 `[ZD, ZG]` 有任意重叠就吞并"，比"完全落在区间内"
  宽松得多。真正的突破笔/回踩笔只要还有一点价格重叠，也会被吞并进
  `pivot.elements`，不会出现在 `pivot.end_time` 之后。`_post_pivot_strokes`
  （`app/services/chan/signals.py`）已经处理了这个问题——把 `pivot.elements[3:]`
  接回真正在 `end_time` 之后的笔。本计划的 `pivot_phase.py` **直接复用**
  `_post_pivot_strokes`（跨模块 import 私有函数是本仓库已有惯例，
  `analyzer.py` 已经在 import `narrative.py` 的 `_volume_readout`）。
- **不要重构 `signals.py`**：那是 CLAUDE.md 标注的高风险模块（不变量+随机模糊
  护栏）。`pivot_phase.py` 独立实现一份等价的"找突破+回踩配对"逻辑，允许和
  `signals.py` 有少量重复，把回归风险限制在新文件内。
- 构造测试用的 `Stroke`/`Fractal`/`MergedCandle` 时，`Pivot.end_time` 必须设为
  `elements[-1].end_time`（即被吞并的最后一段的结束时间），不能设成"最初三段"
  的结束时间——否则 `_post_pivot_strokes` 的时间过滤会把已吞并的突破/回踩笔
  重复算进 `post`。本计划提供的 `_pivot_from` 测试辅助函数已经处理好这一点，
  跟着抄就不会错。
- 全局提交时机：每个 Task 完成后单独 `git commit`，不要攒到最后一起提交。
- iOS 侧改动因为没有可运行的 CI，靠 `xcodebuild build`（或 Xcode 里 ⌘B）验证
  编译通过；没有模拟器时至少保证类型/属性名对得上、`#Preview` 能过编译。

---

## Task 1: 后端 `pivot_phase.py` 状态机核心

**Files:**
- Create: `app/services/chan/pivot_phase.py`
- Test: `tests/services/chan/test_pivot_phase.py`

- [ ] **Step 1: 写测试文件（先写测试，此时 `pivot_phase.py` 还不存在，测试必然导入失败）**

`tests/services/chan/test_pivot_phase.py`:
```python
"""中枢生命周期状态机（pivot_phase）测试。

延续 test_trend_outlook.py 的风格：手搭 Stroke/Pivot/DivergenceResult 直接测
build_pivot_phase，不跑完整分析流程。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.divergence import DivergenceResult
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.pivot import Pivot, find_stroke_pivots
from app.services.chan.pivot_phase import build_pivot_phase
from app.services.chan.signals import generate_buy2_signals
from app.services.chan.stroke import Stroke


def _mc(idx: int, price: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=price, high=price + 1,
                         low=price - 1, close=price, raw_start=idx, raw_end=idx)


def _fx(kind: str, idx: int, price: float) -> Fractal:
    mid = _mc(idx, price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price), right=_mc(idx + 1, price))


def _st(direction: str, idx: int, p0: float, p1: float, confirmed: bool = True) -> Stroke:
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, idx * 10, p0), end=_fx(ek, idx * 10 + 5, p1),
                  confirmed=confirmed)


def _chain(*legs: tuple[str, float, float]) -> list[Stroke]:
    """按顺序生成前后相连的一串笔：leg = (direction, p0, p1)。"""
    return [_st(direction, i, p0, p1) for i, (direction, p0, p1) in enumerate(legs)]


def _pivot_from(strokes: list[Stroke], n_absorbed: int, zg: float, zd: float) -> Pivot:
    """把 strokes 的前 n_absorbed 段当作已被中枢吞并的 elements。

    end_time 必须对齐吞并终点（elements[-1].end_time），否则 _post_pivot_strokes
    的时间过滤会和 elements[3:] 的回填重复计入同一批笔。
    """
    elements = strokes[:n_absorbed]
    return Pivot(zg=zg, zd=zd, gg=zg + 2, dd=zd - 2,
                 start_time=elements[0].start_time, end_time=elements[-1].end_time,
                 level="stroke", elements=elements)


def _div(is_div: bool = False) -> DivergenceResult:
    return DivergenceResult(is_diverged=is_div, type="trend" if is_div else "none",
                             strength="strong" if is_div else "none",
                             area_ratio=0.5 if is_div else 1.0, description="", dif_ratio=0.5)


def _result(strokes, stroke_pivots, divergences) -> ChanAnalysisResult:
    r = ChanAnalysisResult(symbol="T", bars_count=len(strokes))
    r.strokes = strokes
    r.stroke_pivots = stroke_pivots
    r.segment_pivots = []
    r.divergences = divergences or [_div(False) for _ in strokes]
    return r


def test_none_when_not_enough_strokes():
    assert build_pivot_phase(_result([], [], [])) is None


def test_none_when_no_pivot_exists():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 80))
    assert build_pivot_phase(_result(strokes, [], [])) is None


def test_pivot_forming_when_only_three_elements():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92))
    pivot = _pivot_from(strokes, 3, zg=98, zd=92)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp is not None
    assert pp.phase == "pivot_forming"
    assert pp.direction is None
    assert len(pp.checklist) == 2  # 形成中枢(done) + 下一步(pending)，无「当前阶段」行


def test_pivot_oscillating_when_extension_stays_inside_range():
    # 第4段 92->96 全程落在 [90,98] 内，不满足「起点在区间内、终点越界」的突破判据
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92), ("up", 92, 96))
    pivot = _pivot_from(strokes, 4, zg=98, zd=90)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "pivot_oscillating"
    assert pp.direction is None


def test_leaving_when_breakout_crosses_zg_without_retrace_yet():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92), ("up", 92, 110))
    pivot = _pivot_from(strokes, 4, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "leaving"
    assert pp.direction == "up"
    assert len(pp.branches) == 3
    assert {b.outcome for b in pp.branches} == {"type2", "type3", "back_to_range"}


def test_retrace_confirmed_type3_when_retrace_holds_above_zg():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "retrace_confirmed"
    assert pp.direction == "up"
    assert "三买" in pp.phase_label
    assert pp.branches == []


def test_retrace_confirmed_type2_when_retrace_lands_inside_pivot():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 95))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "retrace_confirmed"
    assert "二买" in pp.phase_label


def test_back_to_range_falls_back_to_oscillating():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 85))  # 85 < ZD(91)，反手跌穿对侧
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    pp = build_pivot_phase(_result(strokes, [pivot], []))
    assert pp.phase == "pivot_oscillating"
    assert pp.direction is None


def test_divergence_turn_after_retrace_confirmed_with_matching_divergence():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101), ("up", 101, 130))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)  # 第6段（延续笔）不吞并，走 post 的时间过滤
    divs = [_div(False)] * 5 + [_div(True)]  # 第6段（延续的上升笔）出现背驰
    pp = build_pivot_phase(_result(strokes, [pivot], divs))
    assert pp.phase == "divergence_turn"
    assert pp.direction == "up"


def test_stays_retrace_confirmed_without_matching_divergence():
    strokes = _chain(("down", 100, 90), ("up", 90, 98), ("down", 98, 92),
                      ("up", 92, 110), ("down", 110, 101), ("up", 101, 130))
    pivot = _pivot_from(strokes, 5, zg=99, zd=91)
    divs = [_div(False)] * 6  # 延续笔没有背驰
    pp = build_pivot_phase(_result(strokes, [pivot], divs))
    assert pp.phase == "retrace_confirmed"


def test_cross_check_matches_generate_buy2_signals():
    """交叉验证：pivot_phase 判定出的 outcome 必须和 signals.py 实际产出的信号一致。

    复用 test_signals.py::test_buy2_fires_when_pivot_absorbs_breakout_and_retrace
    同一份真实吞并场景（find_stroke_pivots 产出的真中枢，不是手搭 elements=[]）。
    """
    e0 = _st("down", 0, 100, 90)
    e1 = _st("up", 1, 90, 98)
    e2 = _st("down", 2, 98, 92)
    breakout = _st("up", 3, 92, 110)
    retrace = _st("down", 4, 110, 96)
    strokes = [e0, e1, e2, breakout, retrace]

    pivots = find_stroke_pivots(strokes)
    assert len(pivots) == 1

    sig = generate_buy2_signals(strokes, pivots)
    assert len(sig) == 1 and sig[0].type == "buy2"

    pp = build_pivot_phase(_result(strokes, pivots, []))
    assert pp.phase == "retrace_confirmed"
    assert "二买" in pp.phase_label
```

- [ ] **Step 2: 运行测试，确认因缺少模块而失败**

Run: `uv run pytest tests/services/chan/test_pivot_phase.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.chan.pivot_phase'`（或
`ImportError`）——所有测试收集阶段就失败。

- [ ] **Step 3: 实现 `pivot_phase.py`**

`app/services/chan/pivot_phase.py`:
```python
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
    """post 里还没等到回抽笔、独自满足突破条件的最后一笔（leaving 阶段）。"""
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
```

- [ ] **Step 4: 运行测试，确认全部通过**

Run: `uv run pytest tests/services/chan/test_pivot_phase.py -v`
Expected: 12 个测试全部 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/services/chan/pivot_phase.py tests/services/chan/test_pivot_phase.py
git commit -m "feat(chan): 新增中枢生命周期状态机pivot_phase"
```

---

## Task 2: analyzer.py 接入 pivot_phase + 暴露 walk_type_label/trend_outlook_label

**Files:**
- Modify: `app/services/chan/analyzer.py`
- Test: `tests/services/chan/test_pivot_phase.py`（追加一个端到端集成测试）

- [ ] **Step 1: 追加一个失败的集成测试，验证 analyzer.analyze() 会填充 result.pivot_phase**

在 `tests/services/chan/test_pivot_phase.py` 末尾追加：
```python
def test_analyzer_populates_pivot_phase_end_to_end():
    """端到端：analyzer.analyze() 对真实K线跑出的中枢，pivot_phase 不应为 None。"""
    from app.services.chan.analyzer import ChanAnalyzer

    # 复用 test_signals.py 的 FIG 数据规律：造一段先跌出中枢再反弹的行情，
    # 保证能形成至少一个中枢并产生 pivot_phase。
    bars = [
        {"time": f"2026-01-{i+1:02d}", "open": o, "high": h, "low": low, "close": c, "volume": 1000}
        for i, (o, h, low, c) in enumerate([
            (100, 102, 98, 101), (101, 103, 97, 98), (98, 100, 95, 96),
            (96, 99, 94, 98), (98, 101, 96, 100), (100, 103, 98, 99),
            (99, 102, 97, 101), (101, 108, 100, 107), (107, 112, 105, 110),
            (110, 115, 108, 113), (113, 116, 109, 111), (111, 114, 107, 109),
        ])
    ]
    result = ChanAnalyzer().analyze("TEST", bars)
    assert result.walk_type_label != ""
    assert result.trend_outlook_label != ""
    # 是否产出 pivot_phase 取决于这段合成数据能不能凑出 >=3 笔和一个中枢；
    # 断言字段存在且类型正确，不断言具体 phase（具体 phase 已由 Task 1 的单测覆盖）。
    if result.pivot_phase is not None:
        assert result.pivot_phase.phase in {
            "pivot_forming", "pivot_oscillating", "leaving", "retrace_confirmed", "divergence_turn",
        }
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/services/chan/test_pivot_phase.py::test_analyzer_populates_pivot_phase_end_to_end -v`
Expected: `AttributeError: 'ChanAnalysisResult' object has no attribute 'walk_type_label'`

- [ ] **Step 3: 修改 `ChanAnalysisResult`，新增三个字段**

在 `app/services/chan/analyzer.py` 里找到 `ChanAnalysisResult` 的字段定义（`walk_type: str = "none"` 那一行附近），改为：

```python
    # 走势类型（基于中枢排布）：up_trend / down_trend / consolidation / none
    walk_type: str = "none"
    walk_type_label: str = ""  # 走势类型人话标签（供 iOS「走势」标签行直接展示）
    # 走势展望（延续 vs 转折，缠论走势分类）。取值见 _compute_trend_outlook：
    # 转折向上/转折向下、延续上涨/延续下跌、盘整上破/盘整下破、盘整延续、未明。
    trend_outlook: str = "unclear"
    trend_outlook_label: str = ""  # 走势展望人话标签（同上）
    latest_signal: Signal | None = None
    summary: str = ""
    recommendation: Recommendation | None = None
    # 大白话形态解读（趋势 / 位置 / 量价 / 动能），供普通用户理解当前市场在做什么
    narrative: MarketNarrative | None = None
    # 中枢生命周期状态机：「走到哪一步」，见 pivot_phase.py
    pivot_phase: "PivotPhase | None" = None
```

在文件顶部 import 区加入：
```python
from app.services.chan.pivot_phase import PivotPhase, build_pivot_phase
```

- [ ] **Step 4: 在 `analyze()` 方法尾部（`result.narrative = build_narrative(...)` 那行之后）补充赋值**

找到 `analyzer.py` 里这一段（约第 216-225 行）：
```python
        result.walk_type = classify_walk_type(
            result.segment_pivots if result.segment_pivots else result.stroke_pivots
        )
        result.trend_outlook = self._compute_trend_outlook(result)
        result.current_trend = self._infer_trend_from_strokes(result.strokes, lang)
        result.latest_signal = result.signals[-1] if result.signals else None
        result.summary = self._build_summary(result, lang)
        # 量价需要原始 bars（合并K线不含 volume），故两处都在此传入
        result.recommendation = self._build_recommendation(result, bars, lang)
        result.narrative = build_narrative(result, bars, lang)
```
改为：
```python
        result.walk_type = classify_walk_type(
            result.segment_pivots if result.segment_pivots else result.stroke_pivots
        )
        result.walk_type_label = self._walk_type_label(result.walk_type, lang)
        result.trend_outlook = self._compute_trend_outlook(result)
        result.trend_outlook_label = self._trend_outlook_label(result.trend_outlook, lang)
        result.current_trend = self._infer_trend_from_strokes(result.strokes, lang)
        result.latest_signal = result.signals[-1] if result.signals else None
        result.summary = self._build_summary(result, lang)
        # 量价需要原始 bars（合并K线不含 volume），故两处都在此传入
        result.recommendation = self._build_recommendation(result, bars, lang)
        result.narrative = build_narrative(result, bars, lang)
        result.pivot_phase = build_pivot_phase(result, lang)
```

- [ ] **Step 5: 运行测试确认通过，并跑全量 chan 回归**

Run: `uv run pytest tests/services/chan/ -v`
Expected: 全部 `PASSED`（含既有的 narrative/signals/trend_outlook 测试，确认没有破坏既有行为）

- [ ] **Step 6: Commit**

```bash
git add app/services/chan/analyzer.py tests/services/chan/test_pivot_phase.py
git commit -m "feat(chan): analyzer接入pivot_phase并暴露walk_type_label/trend_outlook_label"
```

---

## Task 3: schemas/chan.py 新增响应字段

**Files:**
- Modify: `app/schemas/chan.py`

- [ ] **Step 1: 新增 `PivotPhaseOut` 系列 schema**

在 `app/schemas/chan.py` 的 `MarketNarrativeOut` 类定义之后插入：
```python
class PhaseChecklistItemOut(BaseModel):
    label: str
    detail: str
    state: Literal["done", "pending"]


class PhaseBranchOut(BaseModel):
    outcome: Literal["type2", "type3", "back_to_range"]
    condition_label: str
    result_label: str


class StageGuideStepOut(BaseModel):
    key: str
    title: str
    detail: str


class StageGuideOut(BaseModel):
    current_index: int
    steps: list[StageGuideStepOut]
    why_it_matters: str


class PivotPhaseOut(BaseModel):
    """中枢生命周期状态机：当前走到哪一步（见 app/services/chan/pivot_phase.py）。"""
    phase: Literal["pivot_forming", "pivot_oscillating", "leaving", "retrace_confirmed", "divergence_turn"]
    phase_label: str
    direction: Optional[Literal["up", "down"]] = None
    pivot: PivotOut
    checklist: list[PhaseChecklistItemOut]
    reason: str
    confirmed: bool = True
    branches: list[PhaseBranchOut] = []
    stage_guide: StageGuideOut
```

- [ ] **Step 2: 在 `ChanAnalysisResponse` 里新增字段**

把 `ChanAnalysisResponse` 类里的：
```python
    walk_type: str = "none"
    # 走势展望（延续 vs 转折）：转折向上/转折向下、延续上涨/延续下跌、
    # 盘整上破/盘整下破、盘整延续、未明（枚举值见 analyzer._compute_trend_outlook）
    trend_outlook: str = "unclear"
    summary: str
    recommendation: Optional[RecommendationOut] = None
    narrative: Optional[MarketNarrativeOut] = None  # 大白话形态解读
    pending_notes: list[str] = []  # 最右侧未确认结构的提示
```
改为：
```python
    walk_type: str = "none"
    walk_type_label: str = ""  # 走势类型人话标签
    # 走势展望（延续 vs 转折）：转折向上/转折向下、延续上涨/延续下跌、
    # 盘整上破/盘整下破、盘整延续、未明（枚举值见 analyzer._compute_trend_outlook）
    trend_outlook: str = "unclear"
    trend_outlook_label: str = ""  # 走势展望人话标签
    summary: str
    recommendation: Optional[RecommendationOut] = None
    narrative: Optional[MarketNarrativeOut] = None  # 大白话形态解读
    pending_notes: list[str] = []  # 最右侧未确认结构的提示
    pivot_phase: Optional[PivotPhaseOut] = None  # 中枢生命周期：走到哪一步
```

- [ ] **Step 3: 语法/类型检查**

Run: `uv run python -c "import app.schemas.chan"`
Expected: 无报错（纯 import 检查新 schema 语法正确）

- [ ] **Step 4: Commit**

```bash
git add app/schemas/chan.py
git commit -m "feat(chan): 新增PivotPhaseOut响应schema"
```

---

## Task 4: api/v1/chan.py 组装转换

**Files:**
- Modify: `app/api/v1/chan.py`

- [ ] **Step 1: 更新 import**

把：
```python
from app.schemas.chan import (
    ChanAnalysisResponse,
    FractalOut,
    GapItemOut,
    GapJobStatus,
    MACDOut,
    MarketNarrativeOut,
    MergedCandleOut,
    PivotOut,
    RecommendationOut,
    SegmentOut,
    SignalOut,
    StrokeOut,
    StructureGapRequest,
    StructureGapResponse,
)
```
改为：
```python
from app.schemas.chan import (
    ChanAnalysisResponse,
    FractalOut,
    GapItemOut,
    GapJobStatus,
    MACDOut,
    MarketNarrativeOut,
    MergedCandleOut,
    PhaseBranchOut,
    PhaseChecklistItemOut,
    PivotOut,
    PivotPhaseOut,
    RecommendationOut,
    SegmentOut,
    SignalOut,
    StageGuideOut,
    StageGuideStepOut,
    StrokeOut,
    StructureGapRequest,
    StructureGapResponse,
)
```

- [ ] **Step 2: 在 `ChanAnalysisResponse(...)` 组装处新增字段**

把：
```python
        current_trend=result.current_trend,
        walk_type=result.walk_type,
        trend_outlook=result.trend_outlook,
        summary=result.summary,
```
改为：
```python
        current_trend=result.current_trend,
        walk_type=result.walk_type,
        walk_type_label=result.walk_type_label,
        trend_outlook=result.trend_outlook,
        trend_outlook_label=result.trend_outlook_label,
        summary=result.summary,
```

在 `recommendation=RecommendationOut(...) if result.recommendation else None,` 这一行之后（`ChanAnalysisResponse(...)` 调用的最后，右括号 `)` 之前）新增：
```python
        pivot_phase=PivotPhaseOut(
            phase=result.pivot_phase.phase,
            phase_label=result.pivot_phase.phase_label,
            direction=result.pivot_phase.direction,
            pivot=PivotOut(
                zg=result.pivot_phase.pivot.zg, zd=result.pivot_phase.pivot.zd,
                gg=result.pivot_phase.pivot.gg, dd=result.pivot_phase.pivot.dd,
                start_time=result.pivot_phase.pivot.start_time,
                end_time=result.pivot_phase.pivot.end_time,
                level=result.pivot_phase.pivot.level,
                confirmed=result.pivot_phase.pivot.confirmed,
            ),
            checklist=[
                PhaseChecklistItemOut(label=c.label, detail=c.detail, state=c.state)
                for c in result.pivot_phase.checklist
            ],
            reason=result.pivot_phase.reason,
            confirmed=result.pivot_phase.confirmed,
            branches=[
                PhaseBranchOut(outcome=b.outcome, condition_label=b.condition_label, result_label=b.result_label)
                for b in result.pivot_phase.branches
            ],
            stage_guide=StageGuideOut(
                current_index=result.pivot_phase.stage_guide.current_index,
                steps=[
                    StageGuideStepOut(key=s.key, title=s.title, detail=s.detail)
                    for s in result.pivot_phase.stage_guide.steps
                ],
                why_it_matters=result.pivot_phase.stage_guide.why_it_matters,
            ),
        ) if result.pivot_phase else None,
```

- [ ] **Step 3: 全量回归**

Run: `uv run pytest tests/ -k chan -v`
Expected: 全部 `PASSED`

Run: `make check`
Expected: `ruff check .` 与 `pyright` 均无报错（新代码类型标注要完整，尤其 `Literal` 值必须和 schema 里的枚举一致）

- [ ] **Step 4: Commit（阶段一后端完成检查点）**

```bash
git add app/api/v1/chan.py
git commit -m "feat(chan): API响应组装pivot_phase字段"
```

在此打个检查点：用真实标的手动跑一次 `GET /api/v1/analysis`（起本地服务 `make dev`，
`curl` 或前端页面均可），确认 `pivot_phase` 字段能正常返回、五个 phase 至少能在
不同标的/日期区间各触发一次，再继续 Task 5（iOS）。

---

## Task 5: iOS Model 扩展

**Files:**
- Modify: `ios/DeepAlphaChan/Models/ChanModels.swift`

- [ ] **Step 1: 在 `MarketNarrative` 结构体之后新增 `PivotPhase` 相关模型**

在 `ios/DeepAlphaChan/Models/ChanModels.swift` 里，`MarketNarrative` struct 定义结束之后（`ChanAnalysis` struct 定义之前）插入：
```swift
/// 中枢生命周期 checklist 里的一行（对应后端 PhaseChecklistItemOut）。
struct PhaseChecklistItem: Codable, Identifiable {
    enum State: String, Codable { case done, pending }
    let label: String
    let detail: String
    let state: State

    var id: String { label }
}

/// 回抽结果的一种可能分支（对应后端 PhaseBranchOut，仅 leaving 阶段非空）。
struct PhaseBranch: Codable, Identifiable {
    let outcome: String  // type2 / type3 / back_to_range
    let conditionLabel: String
    let resultLabel: String

    var id: String { outcome }

    enum CodingKeys: String, CodingKey {
        case outcome
        case conditionLabel = "condition_label"
        case resultLabel = "result_label"
    }
}

/// 阶段讲解弹层里的一个标准步骤（对应后端 StageGuideStepOut）。
struct StageGuideStep: Codable, Identifiable {
    let key: String
    let title: String
    let detail: String

    var id: String { key }
}

/// 阶段讲解弹层内容（对应后端 StageGuideOut）。
struct StageGuide: Codable {
    let currentIndex: Int
    let steps: [StageGuideStep]
    let whyItMatters: String

    enum CodingKeys: String, CodingKey {
        case steps
        case currentIndex = "current_index"
        case whyItMatters = "why_it_matters"
    }
}

/// 中枢生命周期状态机：「走到哪一步」（对应后端 PivotPhaseOut）。
struct PivotPhase: Codable {
    let phase: String  // pivot_forming / pivot_oscillating / leaving / retrace_confirmed / divergence_turn
    let phaseLabel: String
    let direction: String?  // up / down / nil
    let pivot: Pivot
    let checklist: [PhaseChecklistItem]
    let reason: String
    let confirmed: Bool
    let branches: [PhaseBranch]
    let stageGuide: StageGuide

    enum CodingKeys: String, CodingKey {
        case phase, pivot, checklist, reason, confirmed, branches, direction
        case phaseLabel = "phase_label"
        case stageGuide = "stage_guide"
    }
}
```

- [ ] **Step 2: 给 `ChanAnalysis` 新增三个字段**

把 `ChanAnalysis` struct 里的：
```swift
    let currentTrend: String
    // 走势类型（基于中枢排布）：up_trend / down_trend / consolidation / none
    let walkType: String?
    // 走势展望（延续 vs 转折）：reversal_up / reversal_down / continuation_up /
    // continuation_down / breakout_up / breakout_down / range / unclear
    let trendOutlook: String?
    let summary: String
    let recommendation: Recommendation?
    let narrative: MarketNarrative?
    let pendingNotes: [String]

    enum CodingKeys: String, CodingKey {
        case symbol, fractals, strokes, segments, macd, signals, summary, recommendation, narrative
        case barsCount = "bars_count"
        case mergedCandles = "merged_candles"
        case strokePivots = "stroke_pivots"
        case segmentPivots = "segment_pivots"
        case currentTrend = "current_trend"
        case walkType = "walk_type"
        case trendOutlook = "trend_outlook"
        case pendingNotes = "pending_notes"
    }
```
改为：
```swift
    let currentTrend: String
    // 走势类型（基于中枢排布）：up_trend / down_trend / consolidation / none
    let walkType: String?
    let walkTypeLabel: String?
    // 走势展望（延续 vs 转折）：reversal_up / reversal_down / continuation_up /
    // continuation_down / breakout_up / breakout_down / range / unclear
    let trendOutlook: String?
    let trendOutlookLabel: String?
    let summary: String
    let recommendation: Recommendation?
    let narrative: MarketNarrative?
    let pendingNotes: [String]
    let pivotPhase: PivotPhase?

    enum CodingKeys: String, CodingKey {
        case symbol, fractals, strokes, segments, macd, signals, summary, recommendation, narrative
        case barsCount = "bars_count"
        case mergedCandles = "merged_candles"
        case strokePivots = "stroke_pivots"
        case segmentPivots = "segment_pivots"
        case currentTrend = "current_trend"
        case walkType = "walk_type"
        case walkTypeLabel = "walk_type_label"
        case trendOutlook = "trend_outlook"
        case trendOutlookLabel = "trend_outlook_label"
        case pendingNotes = "pending_notes"
        case pivotPhase = "pivot_phase"
    }
```

- [ ] **Step 3: 编译检查（没有单元测试目标时，用编译代替）**

Run: `cd ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS Simulator' build 2>&1 | tail -40`
Expected: 编译报错，因为 `PreviewMock.swift` 里的 `ChanAnalysis(...)` 调用缺少新增的必填参数——这是预期的，下一个 Task 修复。

- [ ] **Step 4: Commit**

```bash
git add ios/DeepAlphaChan/Models/ChanModels.swift
git commit -m "feat(chan-ios): 新增PivotPhase等模型承接后端状态机字段"
```

---

## Task 6: iOS PreviewMock 补充

**Files:**
- Modify: `ios/DeepAlphaChan/Views/Analysis/PreviewMock.swift`

- [ ] **Step 1: 给 `PreviewMock.analysis` 补上新字段**

把 `PreviewMock.swift` 里 `ChanAnalysis(...)` 调用的：
```swift
            currentTrend: "up",
            walkType: "up_trend",
            trendOutlook: "continuation_up",
            summary: "近期走出一段向上线段，价格站上前一中枢上沿并完成回踩确认，结构偏强。当前处于线段延伸阶段，尚未出现同级别背驰。",
```
改为：
```swift
            currentTrend: "up",
            walkType: "up_trend",
            walkTypeLabel: "当前为上涨趋势（中枢依次抬高）",
            trendOutlook: "continuation_up",
            trendOutlookLabel: "上涨走势延续",
            summary: "近期走出一段向上线段，价格站上前一中枢上沿并完成回踩确认，结构偏强。当前处于线段延伸阶段，尚未出现同级别背驰。",
```

在 `pendingNotes: [...]` 参数之后（`ChanAnalysis(...)` 调用的最后，右括号之前）新增：
```swift
            pivotPhase: PivotPhase(
                phase: "leaving",
                phaseLabel: "向上离开中枢",
                direction: "up",
                pivot: Pivot(zg: 388.0, zd: 372.0, gg: 390.5, dd: 370.2,
                             startTime: "2026-05-12", endTime: "2026-06-20",
                             level: .stroke, confirmed: true),
                checklist: [
                    PhaseChecklistItem(label: "形成中枢", detail: "372.00–388.00", state: .done),
                    PhaseChecklistItem(label: "向上离开中枢", detail: "现价 392.16 已站上 ZG 388.00", state: .done),
                    PhaseChecklistItem(label: "等待离开段走完后回抽确认", detail: "", state: .pending),
                ],
                reason: "现价 392.16 已站上 ZG 388.00，最新向上笔离开了中枢区间。",
                confirmed: true,
                branches: [
                    PhaseBranch(outcome: "type3", conditionLabel: "回踩守住 ZG 388.00 以上，不回中枢",
                                resultLabel: "确认三买（趋势确认，最强）"),
                    PhaseBranch(outcome: "type2", conditionLabel: "回踩落在中枢区间内，未破 ZD 372.00",
                                resultLabel: "确认二买（中枢升级，弱于三买）"),
                    PhaseBranch(outcome: "back_to_range", conditionLabel: "回踩跌破 ZD 372.00，重新进入中枢",
                                resultLabel: "假突破，回到中枢震荡"),
                ],
                stageGuide: StageGuide(
                    currentIndex: 2,
                    steps: [
                        StageGuideStep(key: "pivot_forming", title: "中枢形成", detail: "三段重叠围出 372.00–388.00"),
                        StageGuideStep(key: "pivot_oscillating", title: "中枢震荡", detail: "区间内反复，中枢延伸"),
                        StageGuideStep(key: "leaving", title: "离开段", detail: "向上离开中枢，候选第三类买点"),
                        StageGuideStep(key: "retrace_confirmed", title: "回抽确认", detail: "回抽不进中枢 → 确认三买"),
                        StageGuideStep(key: "divergence_turn", title: "背驰/转折", detail: "趋势末端背驰 → 一类买卖点"),
                    ],
                    whyItMatters: "离开段是缠论趋势能否延续的分水岭：向上离开中枢后若回抽不进中枢，就确认三买、中枢升级、趋势打开；若回抽跌回中枢，则回到震荡。"
                )
            ),
```

- [ ] **Step 2: 编译检查**

Run: `cd ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS Simulator' build 2>&1 | tail -40`
Expected: 编译通过（`BUILD SUCCEEDED`）

- [ ] **Step 3: Commit**

```bash
git add ios/DeepAlphaChan/Views/Analysis/PreviewMock.swift
git commit -m "test(chan-ios): PreviewMock补充pivotPhase示例数据"
```

---

## Task 7: iOS `AnalysisSection` 改版——「走到哪一步」区块 + 走势标签

**Files:**
- Modify: `ios/DeepAlphaChan/Views/Analysis/AnalysisSection.swift`
- Create: `ios/DeepAlphaChan/Views/Analysis/PivotPhaseGuideSheet.swift`（本 Task 先建文件占位，完整实现见 Task 8）

- [ ] **Step 1: 先在 `PivotPhaseGuideSheet.swift` 放一个最小占位实现，供本 Task 编译通过**

`ios/DeepAlphaChan/Views/Analysis/PivotPhaseGuideSheet.swift`:
```swift
import SwiftUI

/// 「走到哪一步」阶段徽标点击后弹出的讲解层。完整实现见 Task 8。
struct PivotPhaseGuideSheet: View {
    let pivotPhase: PivotPhase

    var body: some View {
        Text(pivotPhase.phaseLabel)
    }
}
```

- [ ] **Step 2: 改版 `AnalysisSection.swift` 的 `statusCard`，并新增独立的 `PivotPhaseBlock` 子 View**

（这块逻辑需要自己的 `@State` 管理讲解 sheet 的呈现——`@State` 只能声明在
`View` 的属性上，不能是 `AnalysisSection` 里一个普通方法的局部变量，所以直接
写成独立的子 View，不是 `AnalysisSection` 的私有方法。）

把 `AnalysisSection.swift` 里的：
```swift
    /// 当前状态：大白话一句话 → 各项事实依据 → 一行结构统计，只陈述事实不下结论。
    private var statusCard: some View {
        CollapsibleCard(title: L("当前状态"), systemImage: "waveform.path.ecg",
                        defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 14) {
                // 结构没成形（笔太少）时没有大白话解读，退回后端摘要
                Text(analysis.narrative?.headline ?? analysis.summary)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let rec = analysis.recommendation, !rec.reasons.isEmpty {
                    Divider().overlay(Theme.border)
                    BulletList(title: L("依据"), items: rec.reasons, color: Theme.textSecondary)
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
```
改为：
```swift
    /// 当前状态：大白话一句话 → 走到哪一步 → 各项事实依据 → 走势标签 → 结构统计，
    /// 只陈述事实不下结论。
    private var statusCard: some View {
        CollapsibleCard(title: L("当前状态"), systemImage: "waveform.path.ecg",
                        defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 14) {
                // 结构没成形（笔太少）时没有大白话解读，退回后端摘要
                Text(analysis.narrative?.headline ?? analysis.summary)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let phase = analysis.pivotPhase {
                    Divider().overlay(Theme.border)
                    PivotPhaseBlock(phase: phase)
                }

                if let rec = analysis.recommendation, !rec.reasons.isEmpty {
                    Divider().overlay(Theme.border)
                    BulletList(title: L("依据"), items: rec.reasons, color: Theme.textSecondary)
                }

                if analysis.walkTypeLabel != nil || analysis.trendOutlookLabel != nil {
                    Divider().overlay(Theme.border)
                    walkTypeChips
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// 「走势」标签行：走势类型 + 走势展望的人话标签（这两个字段此前未被 UI 消费）。
    private var walkTypeChips: some View {
        HStack(spacing: 8) {
            if let label = analysis.walkTypeLabel { Chip(text: label, color: Theme.accent) }
            if let label = analysis.trendOutlookLabel { Chip(text: label, color: Theme.segment) }
        }
    }
```

在 `AnalysisSection` struct 的闭合 `}` 之后（文件末尾）追加一个独立的
`PivotPhaseBlock` View——需要自己的 `@State` 管理讲解 sheet 的呈现，`@State`
只能声明在 `View` 的属性上，不能是 `AnalysisSection` 里一个普通方法的局部
变量，所以不写成 `AnalysisSection` 的私有方法：
```swift
/// 「走到哪一步」区块：阶段徽标（点击弹讲解）+ checklist + 因为 + 分支说明。
///
/// 独立成子 View 而不是 AnalysisSection 的私有方法：需要自己的 @State 管理
/// 讲解 sheet 的呈现，方法内部不能声明 @State。
private struct PivotPhaseBlock: View {
    let phase: PivotPhase
    @State private var showGuide = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Text(L("走到哪一步"))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Theme.textSecondary)
                Spacer()
                Button {
                    showGuide = true
                } label: {
                    HStack(spacing: 4) {
                        Text(phase.phaseLabel)
                        Image(systemName: "info.circle")
                    }
                }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(Theme.accent.opacity(0.15))
                .foregroundColor(Theme.accent)
                .clipShape(Capsule())
            }

            VStack(alignment: .leading, spacing: 6) {
                ForEach(phase.checklist) { item in
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: item.state == .done ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(item.state == .done ? Theme.accent : Theme.textSecondary)
                            .font(.system(size: 13))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.label)
                                .font(.system(size: 13, weight: item.state == .done ? .medium : .regular))
                                .foregroundColor(item.state == .done ? Theme.textPrimary : Theme.textSecondary)
                            if !item.detail.isEmpty {
                                Text(item.detail)
                                    .font(.caption2)
                                    .foregroundColor(Theme.textSecondary)
                            }
                        }
                    }
                }
            }

            HStack(alignment: .top, spacing: 4) {
                Text(L("因为")).font(.caption).foregroundColor(Theme.accent)
                Text(phase.reason).font(.caption).foregroundColor(Theme.textSecondary)
            }

            if !phase.branches.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(phase.branches) { branch in
                        Text("↳ \(branch.conditionLabel) → \(branch.resultLabel)")
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                    }
                }
            }
        }
        .sheet(isPresented: $showGuide) {
            NavigationStack { PivotPhaseGuideSheet(pivotPhase: phase) }
                .preferredColorScheme(.dark)
        }
    }
}
```

- [ ] **Step 3: 编译检查**

Run: `cd ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS Simulator' build 2>&1 | tail -40`
Expected: `BUILD SUCCEEDED`

- [ ] **Step 4: Commit**

```bash
git add ios/DeepAlphaChan/Views/Analysis/AnalysisSection.swift ios/DeepAlphaChan/Views/Analysis/PivotPhaseGuideSheet.swift
git commit -m "feat(chan-ios): AnalysisSection新增走到哪一步区块与走势标签"
```

---

## Task 8: iOS `PivotPhaseGuideSheet` 完整实现

**Files:**
- Modify: `ios/DeepAlphaChan/Views/Analysis/PivotPhaseGuideSheet.swift`

- [ ] **Step 1: 用完整实现替换 Task 7 里的占位内容**

把整个 `PivotPhaseGuideSheet.swift` 替换为：
```swift
import SwiftUI

/// 「走到哪一步」阶段徽标点击后弹出的讲解层：标准五步阶梯 + 为什么关键 +
/// 现在满足到哪了。
///
/// 「现在满足到哪了」直接复用主页面的 `checklist`（同一份数据源，只是图标从
/// ✓/○ 换成 ✅/⚠️），不重复建模——两处一旦各自维护，迟早会在某次改动后对不上。
struct PivotPhaseGuideSheet: View {
    let pivotPhase: PivotPhase
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                stageStepper
                whyItMattersSection
                satisfiedSoFarSection
                Text(L("点图上的笔/线段/中枢/买卖点，可逐个看它在当前图形怎么形成"))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
            .padding(16)
        }
        .background(Theme.background)
        .navigationTitle(L("%@·讲解", pivotPhase.phaseLabel))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                }
            }
        }
    }

    /// 拼「标题（你在这）」——用字符串拼接而不是嵌套插值，避免圆括号和全角括号
    /// 混在一起数错层数。
    private func currentStepTitle(_ title: String) -> String {
        title + "（" + L("你在这") + "）"
    }

    private var stageStepper: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(L("你在标准阶段的哪一步"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
            VStack(alignment: .leading, spacing: 14) {
                ForEach(Array(pivotPhase.stageGuide.steps.enumerated()), id: \.element.id) { idx, step in
                    let isCurrent = idx == pivotPhase.stageGuide.currentIndex
                    let isPast = idx < pivotPhase.stageGuide.currentIndex
                    HStack(alignment: .top, spacing: 10) {
                        Circle()
                            .fill(isCurrent ? Theme.segment : (isPast ? Theme.accent : Theme.textSecondary.opacity(0.3)))
                            .frame(width: 10, height: 10)
                            .padding(.top, 4)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(isCurrent ? currentStepTitle(step.title) : step.title)
                                .font(.system(size: 14, weight: isCurrent ? .semibold : .regular))
                                .foregroundColor(isCurrent ? Theme.segment : Theme.textPrimary)
                            Text(step.detail)
                                .font(.caption)
                                .foregroundColor(Theme.textSecondary)
                        }
                    }
                }
            }
        }
    }

    private var whyItMattersSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("这一步为什么关键？"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.accent)
            Text(pivotPhase.stageGuide.whyItMatters)
                .font(.system(size: 14))
                .foregroundColor(Theme.textPrimary)
                .lineSpacing(4)
        }
    }

    private var satisfiedSoFarSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("现在满足到哪了？"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
            ForEach(pivotPhase.checklist) { item in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: item.state == .done ? "checkmark.circle.fill" : "exclamationmark.circle")
                        .foregroundColor(item.state == .done ? .green : Theme.segment)
                        .font(.system(size: 14))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.state == .done ? L("已满足：%@", item.label) : L("尚未满足：%@", item.label))
                            .font(.system(size: 13))
                            .foregroundColor(Theme.textPrimary)
                        if !item.detail.isEmpty {
                            Text(item.detail).font(.caption2).foregroundColor(Theme.textSecondary)
                        }
                    }
                }
            }
        }
    }
}
```

- [ ] **Step 2: 编译检查**

Run: `cd ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS Simulator' build 2>&1 | tail -40`
Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: SwiftUI 预览走查（有 Xcode 环境时）**

在 `PreviewMock.swift` 末尾的 `#Preview` 区新增一个预览，跑一遍 `PivotPhaseGuideSheet`：
```swift
#Preview("阶段讲解") {
    NavigationStack {
        PivotPhaseGuideSheet(pivotPhase: PreviewMock.analysis.pivotPhase!)
    }
    .preferredColorScheme(.dark)
}
```
在 Xcode 画布里打开 `PreviewMock.swift`，确认「阶段讲解」预览渲染正常：五步
stepper 高亮在"离开段"、"为什么关键"文案完整显示、"现在满足到哪了"列出三条
checklist。同时打开「形态分析」预览，确认 `AnalysisSection` 里新增的"走到哪
一步"区块、阶段徽标、走势 chip 都正常显示且不和已有内容重叠。

- [ ] **Step 4: Commit**

```bash
git add ios/DeepAlphaChan/Views/Analysis/PivotPhaseGuideSheet.swift ios/DeepAlphaChan/Views/Analysis/PreviewMock.swift
git commit -m "feat(chan-ios): 完整实现PivotPhaseGuideSheet阶段讲解弹层"
```

---

## Task 9: 真机/模拟器走查 + 分享长图回归

**Files:** 无代码改动，纯验证

- [ ] **Step 1: 真实数据走查五个 phase**

起本地后端 `make dev`，登录 App（模拟器或真机），对以下场景各挑一支真实标的
（可通过调整日期区间人为凑出不同 phase，例如选一段刚形成中枢的窗口 vs 选一段
明显突破后回踩的窗口）验证一遍：

- `pivot_forming` / `pivot_oscillating`：阶段徽标显示"中枢震荡"，checklist 只有
  两行（形成中枢 done + 下一步 pending），无分支说明
- `leaving`：阶段徽标显示"向上/向下离开中枢"，checklist 三行，底部有 3 条分支箭头
- `retrace_confirmed`：阶段徽标显示"确认二/三买（卖）"，无分支说明
- `divergence_turn`：阶段徽标显示"顶/底背驰，趋势可能转折"
- 点开阶段徽标，确认讲解 sheet 的五步 stepper 正确高亮当前步骤，"现在满足到哪了"
  与主页面 checklist 一致

- [ ] **Step 2: 边界场景**

- 找一支笔数 < 3（刚上市或选了很短的日期区间）的标的，确认"走到哪一步"区块和
  "走势"标签整体不显示，卡片退化为改版前的样式，没有空态占位或崩溃
- 确认分享长图（点击分享按钮生成的预览图）里，"走到哪一步"区块和走势 chip 能
  正常出现在长图中（纯 SwiftUI 布局，`ImageRenderer` 不会漏渲染）

- [ ] **Step 3: 记录走查结果**

如果走查中发现任何 phase 判定看起来不合理（比如某支标的显示的 phase 和图表上
肉眼判断的走势明显矛盾），记录下具体标的+日期区间+期望 phase+实际 phase，作为
后续修正的输入——不在本 Task 里改代码，只记录。
