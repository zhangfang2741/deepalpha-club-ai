"""市场周期阶段判定：吸筹 / 拉升 / 派发 / 下跌，以及交易区间内 A–E 子阶段。"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.wyckoff.structure import StructureResult, TradingRange


# 市场周期四阶段
STAGE_ACCUMULATION = "accumulation"   # 吸筹
STAGE_MARKUP = "markup"               # 拉升
STAGE_DISTRIBUTION = "distribution"   # 派发
STAGE_MARKDOWN = "markdown"           # 下跌
STAGE_UNKNOWN = "undetermined"        # 结构不明

STAGE_LABEL: dict[str, str] = {
    STAGE_ACCUMULATION: "吸筹（Accumulation）",
    STAGE_MARKUP: "拉升（Markup）",
    STAGE_DISTRIBUTION: "派发（Distribution）",
    STAGE_MARKDOWN: "下跌（Markdown）",
    STAGE_UNKNOWN: "结构不明",
}

# 交易区间内子阶段释义
PHASE_LABEL: dict[str, str] = {
    "A": "A 阶段：止跌/止涨，前趋势停止",
    "B": "B 阶段：构筑原因，区间内反复震荡",
    "C": "C 阶段：测试（弹簧/冲高），主力最后洗盘",
    "D": "D 阶段：趋势在区间内确立（SOS/SOW）",
    "E": "E 阶段：价格离开区间，趋势展开",
}


@dataclass
class PhaseResult:
    stage: str            # 四阶段之一
    stage_label: str
    phase: str            # A–E（区间内），突破后为 E
    phase_label: str
    breakout: str         # "up" | "down" | "none"


def determine_phase(structure: StructureResult, last_price: float) -> PhaseResult:
    """结合结构、最新事件与当前价格，判定所处阶段。"""
    tr = structure.trading_range
    if tr is None or structure.context == "undetermined":
        return PhaseResult(
            stage=STAGE_UNKNOWN, stage_label=STAGE_LABEL[STAGE_UNKNOWN],
            phase="", phase_label="", breakout="none",
        )

    # 突破判定
    break_buf = tr.width * 0.15 if tr.width > 0 else tr.resistance * 0.01
    broke_up = last_price > tr.resistance + break_buf
    broke_down = last_price < tr.support - break_buf

    latest_phase = structure.events[-1].phase if structure.events else "B"

    if tr.kind == "accumulation":
        if broke_up:
            return _mk(STAGE_MARKUP, "E", "up")
        if broke_down:
            # 跌破吸筹支撑 → 结构失败，转为下跌
            return _mk(STAGE_MARKDOWN, "E", "down")
        return _mk(STAGE_ACCUMULATION, latest_phase, "none")

    # distribution
    if broke_down:
        return _mk(STAGE_MARKDOWN, "E", "down")
    if broke_up:
        return _mk(STAGE_MARKUP, "E", "up")
    return _mk(STAGE_DISTRIBUTION, latest_phase, "none")


def _mk(stage: str, phase: str, breakout: str) -> PhaseResult:
    return PhaseResult(
        stage=stage, stage_label=STAGE_LABEL[stage],
        phase=phase, phase_label=PHASE_LABEL.get(phase, ""), breakout=breakout,
    )


def position_in_range(tr: TradingRange | None, last_price: float) -> str:
    """当前价格在交易区间中的位置描述。"""
    if tr is None or tr.width <= 0:
        return ""
    pct = (last_price - tr.support) / tr.width
    if pct < 0:
        return f"当前价 {last_price:.2f} 已跌破区间下沿 {tr.support:.2f}"
    if pct > 1:
        return f"当前价 {last_price:.2f} 已突破区间上沿 {tr.resistance:.2f}"
    return (
        f"当前价 {last_price:.2f} 位于区间 "
        f"{tr.support:.2f}–{tr.resistance:.2f} 的 {pct * 100:.0f}% 处"
    )
