"""缠论「级别进度」：把两个结构级别（笔级 / 线段级）当前走到哪一步用文字讲清楚。

用户在图上能看到笔 / 线段 / 中枢，却看不懂「现在是哪个级别、走到第几步」。这里做一层
**只读**的汇总：读已经算好的结构（笔、线段、各级中枢、各级背驰、买卖点），产出每个
级别的「时间周期标签 + 已形成几个中枢 + 走势类型 + 当前阶段（延伸 / 离开 / 背驰）」
文字提示，直接回答用户的诉求——中枢、买卖点分别属于哪个级别（如 1D / 1W），
每个级别走到哪一步了。

刻意规则化、只描述现状、不预测涨跌，也**不改动任何缠论算法**。文案随 lang（zh / en）切换。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.chan.i18n import is_en, pick
from app.services.chan.pivot import classify_walk_type

if TYPE_CHECKING:
    from app.services.chan.analyzer import ChanAnalysisResult
    from app.services.chan.divergence import DivergenceResult
    from app.services.chan.pivot import Pivot

# freq → 各结构级别对应的时间周期标签。缠论递归关系：本级别的线段 ≈ 高一级别的笔，
# 故「笔」对应本级别（图上所选周期），「线段」对应高一级别（更大的时间周期）。
_TF_LABELS: dict[str, dict[str, str]] = {
    "daily": {"stroke": "日线 1D", "segment": "周线 1W"},
    "weekly": {"stroke": "周线 1W", "segment": "月线 1M"},
}
_TF_LABELS_EN: dict[str, dict[str, str]] = {
    "daily": {"stroke": "Daily 1D", "segment": "Weekly 1W"},
    "weekly": {"stroke": "Weekly 1W", "segment": "Monthly 1M"},
}


@dataclass
class LevelProgress:
    """单个结构级别当前的进度快照（纯文字描述，不含操作建议）。"""
    level: Literal["stroke", "segment"]  # 结构级别代码
    level_name: str      # 级别名（笔级别 / 线段级别）
    tf_label: str        # 时间周期标签（日线 1D / 周线 1W ...）
    pivot_count: int     # 已形成的有效中枢数
    walk_type: str       # up_trend / down_trend / consolidation / none
    walk_label: str      # 走势类型人话
    stage: str           # 阶段代码（见 _one_level）
    stage_label: str     # 当前「走到哪一步」（一句话）
    detail: str          # 更完整的一句话汇总（级别 + 走势 + 阶段）
    latest_signal_label: str | None = None  # 该级别最近买卖点（仅笔级别有）


def _tf_label(freq: str, level: str, lang: str) -> str:
    table = _TF_LABELS_EN if is_en(lang) else _TF_LABELS
    return table.get(freq, table["daily"]).get(level, level)


def _recent_divergence_dir(
    units: list, divergences: list[DivergenceResult]
) -> str | None:
    """最近一次背驰发生在上升段还是下降段上（顶背驰 / 底背驰）。

    units 与 divergences 一一对应（笔↔笔级背驰、线段↔线段级背驰）。
    """
    direction: str | None = None
    for u, dv in zip(units, divergences, strict=False):
        if dv.is_diverged:
            direction = u.direction
    return direction


def _one_level(
    level: Literal["stroke", "segment"],
    units: list,
    pivots: list[Pivot],
    divergences: list[DivergenceResult],
    result: ChanAnalysisResult,
    freq: str,
    lang: str,
    *,
    include_signals: bool = False,
) -> LevelProgress:
    en = is_en(lang)
    level_name = (
        pick(lang, "笔级别", "Stroke level")
        if level == "stroke"
        else pick(lang, "线段级别", "Segment level")
    )
    tf_label = _tf_label(freq, level, lang)
    walk_type = classify_walk_type(pivots)
    walk_label = {
        "up_trend": pick(lang, "上涨趋势", "Uptrend"),
        "down_trend": pick(lang, "下跌趋势", "Downtrend"),
        "consolidation": pick(lang, "盘整", "Consolidation"),
        "none": pick(lang, "无中枢", "No pivot"),
    }[walk_type]

    valid = [p for p in pivots if p.is_valid]
    n = len(valid)
    last_price = result.merged_candles[-1].close if result.merged_candles else 0.0
    div_dir = _recent_divergence_dir(units, divergences)

    # ---- 阶段判定：当前级别走到哪一步 ----
    if not units:
        stage = "forming"
        stage_label = pick(lang, "结构尚未走出，等待第一段成形",
                           "Structure not yet formed; waiting for the first leg")
    elif n == 0:
        stage = "no_pivot"
        up = units[-1].direction == "up"
        stage_label = pick(
            lang,
            f"尚未形成中枢，处于{'向上' if up else '向下'}单边推进",
            f"No pivot yet; in a one-way {'up' if up else 'down'} move",
        )
    else:
        last = valid[-1]
        if not last.confirmed:
            stage = "building"
            stage_label = pick(
                lang,
                f"第 {n} 个中枢延伸中（{last.zd:.2f}~{last.zg:.2f}）",
                f"Pivot #{n} is extending ({last.zd:.2f}–{last.zg:.2f})",
            )
        elif last_price > last.zg:
            stage = "leaving_up"
            stage_label = pick(
                lang,
                f"已向上离开第 {n} 个中枢（离开段进行中）",
                f"Left pivot #{n} to the upside (departure leg underway)",
            )
        elif last_price < last.zd:
            stage = "leaving_down"
            stage_label = pick(
                lang,
                f"已向下离开第 {n} 个中枢（离开段进行中）",
                f"Left pivot #{n} to the downside (departure leg underway)",
            )
        else:
            stage = "inside"
            stage_label = pick(
                lang,
                f"回到第 {n} 个中枢区间内震荡",
                f"Back inside pivot #{n}, oscillating",
            )
        # 背驰叠加：离开 / 延伸段若出现同向背驰，提示接近转折
        if div_dir == "up":
            stage_label += pick(lang, "，接近顶背驰", "; nearing a top divergence")
        elif div_dir == "down":
            stage_label += pick(lang, "，接近底背驰", "; nearing a bottom divergence")

    latest_signal_label: str | None = None
    if include_signals and result.signals:
        sig = result.signals[-1]
        latest_signal_label = f"{sig.label}（{sig.time}）" if not en else f"{sig.label} ({sig.time})"

    # ---- 一句话汇总 ----
    if en:
        detail = f"{level_name} · {tf_label}: {walk_label}, {n} pivot(s) — {stage_label}."
    else:
        detail = f"{level_name}（{tf_label}）：{walk_label}，已形成 {n} 个中枢——{stage_label}。"

    return LevelProgress(
        level=level,
        level_name=level_name,
        tf_label=tf_label,
        pivot_count=n,
        walk_type=walk_type,
        walk_label=walk_label,
        stage=stage,
        stage_label=stage_label,
        detail=detail,
        latest_signal_label=latest_signal_label,
    )


def build_level_progress(
    result: ChanAnalysisResult, freq: str = "daily", lang: str = "zh"
) -> list[LevelProgress]:
    """产出各结构级别（笔级 / 线段级）的进度快照，从低级别到高级别排列。

    - 笔级别：本级别（图上所选周期），带最近买卖点（三类买卖点均在笔级别生成）。
    - 线段级别：高一级别，仅在已识别出线段时给出。
    数据不足（无笔）时返回空列表，由上层决定是否展示。
    """
    if not result.strokes:
        return []

    levels: list[LevelProgress] = [
        _one_level(
            "stroke",
            result.strokes,
            result.stroke_pivots,
            result.divergences,
            result,
            freq,
            lang,
            include_signals=True,
        )
    ]
    if result.segments:
        levels.append(
            _one_level(
                "segment",
                result.segments,
                result.segment_pivots,
                result.segment_divergences,
                result,
                freq,
                lang,
            )
        )
    return levels
