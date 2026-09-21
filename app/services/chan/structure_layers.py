"""按「笔/线段/中枢/买卖点」四个结构层，各给一句「现在是什么状态」的摘要。

给 iOS 详情页「查看判断依据」展开区用：用户想知道结论怎么来的，按结构层拆开
比一份扁平的加权依据列表更好读——每层此刻处于什么状态、为什么，一目了然。

中枢层直接复用 `pivot_phase` 的判定结果（`phase_label`/`reason`），不重新算
一遍——避免同一件事在两处各判一次、迟早对不上。笔/线段层看最新一笔/线段是否
已确认；买卖点层看最新一个信号。结构没成形的层（比如笔数不够、连一条线段
都构不成）不返回对应条目，不硬凑。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.chan.i18n import pick

if TYPE_CHECKING:
    from app.services.chan.analyzer import ChanAnalysisResult

Layer = Literal["stroke", "segment", "pivot", "signal"]


@dataclass
class StructureLayer:
    layer: Layer
    label: str
    title: str
    detail: str


def _stroke_layer(result: "ChanAnalysisResult", lang: str) -> StructureLayer | None:
    if not result.strokes:
        return None
    last = result.strokes[-1]
    up = last.direction == "up"
    dir_zh, dir_en = ("向上", "Up") if up else ("向下", "Down")
    if last.confirmed:
        title = pick(lang, f"{dir_zh}笔已确认", f"{dir_en}-leg confirmed")
        detail = pick(lang, "已有后续结构锁定该笔端点，形态不会再变。",
                       "A later structure has locked this leg's endpoint; it won't change further.")
    else:
        start_zh, start_en = ("底", "bottom") if last.start.type == "bottom" else ("顶", "top")
        end_zh, end_en = ("顶", "top") if last.end.type == "top" else ("底", "bottom")
        title = pick(lang, f"{dir_zh}笔形成中", f"{dir_en}-leg forming")
        detail = pick(lang,
            f"最新{start_zh}分型后向{'上' if up else '下'}延伸，{end_zh}分型尚未确认。",
            f"Extending {'up' if up else 'down'} after the latest {start_en} fractal; "
            f"the {end_en} fractal isn't confirmed yet.")
    return StructureLayer(layer="stroke", label=pick(lang, "笔", "Stroke"), title=title, detail=detail)


def _segment_layer(result: "ChanAnalysisResult", lang: str) -> StructureLayer | None:
    if not result.segments:
        return None
    last = result.segments[-1]
    up = last.direction == "up"
    dir_zh, dir_en = ("向上", "Up") if up else ("向下", "Down")
    if last.confirmed:
        title = pick(lang, f"{dir_zh}线段已确认", f"{dir_en} segment confirmed")
        detail = pick(lang, "后续反向线段已确认，结构已定。",
                       "A later opposite-direction segment confirmed it; the structure is settled.")
    else:
        title = pick(lang, f"{dir_zh}线段未结束", f"{dir_en} segment still open")
        detail = pick(lang, "当前笔尚未破坏线段结构，线段延续。",
                       "The current leg hasn't broken the segment's structure yet; it continues.")
    return StructureLayer(layer="segment", label=pick(lang, "线段", "Segment"), title=title, detail=detail)


def _pivot_layer(result: "ChanAnalysisResult", lang: str) -> StructureLayer | None:
    phase = result.pivot_phase
    if phase is None:
        return None
    return StructureLayer(layer="pivot", label=pick(lang, "中枢", "Pivot"),
                           title=phase.phase_label, detail=phase.reason)


def _signal_layer(result: "ChanAnalysisResult", lang: str) -> StructureLayer | None:
    if not result.signals:
        return None
    last = result.signals[-1]
    if last.confirmed:
        title = last.label
        detail = pick(lang, "已被后续走势确认，形态成立。", "Confirmed by the subsequent move; the pattern holds.")
    else:
        title = pick(lang, f"{last.label}候选", f"{last.label} (candidate)")
        detail = pick(lang, "落在未确认笔上，属左侧预判。", "Sits on an unconfirmed leg — a left-side call.")
    return StructureLayer(layer="signal", label=pick(lang, "买卖点", "Signal"), title=title, detail=detail)


def build_structure_layers(result: "ChanAnalysisResult", lang: str = "zh") -> list[StructureLayer]:
    """按 笔→线段→中枢→买卖点 的顺序返回已成形的结构层，缺的层直接跳过。"""
    candidates = (
        _stroke_layer(result, lang),
        _segment_layer(result, lang),
        _pivot_layer(result, lang),
        _signal_layer(result, lang),
    )
    return [layer for layer in candidates if layer is not None]


def _price_position_clause(result: "ChanAnalysisResult", lang: str) -> str | None:
    """现价相对最新中枢的位置：站上/跌破/运行在区间内。取不到中枢或现价时返回 None。"""
    phase = result.pivot_phase
    if phase is None or not result.merged_candles:
        return None
    price = result.merged_candles[-1].close
    pivot = phase.pivot
    if price > pivot.zg:
        return pick(lang, "现价站上中枢上方", "price is sitting above the pivot")
    if price < pivot.zd:
        return pick(lang, "现价跌破中枢下方", "price has broken below the pivot")
    return pick(lang, "现价运行在中枢区间内", "price is sitting inside the pivot range")


def build_structure_headline(result: "ChanAnalysisResult", lang: str = "zh") -> str | None:
    """按「线段+笔+中枢位置+买卖点」四个维度拼一句摘要，供详情页「当前状态」用。

    这是固定模板句，不是自由文本生成——每个分句直接对应 structure_layers 里
    同一份判定依据（线段/笔方向、pivot_phase 的中枢位置、最新买卖点），保证
    「当前状态」这句话和下面「查看判断依据」展开的四层结论是同一套事实的两种
    呈现，不会读起来像两套互相独立的算法各说各话。

    结构没成形（缺线段或缺笔）时返回 None，调用方退回旧的 narrative.headline。
    """
    if not result.segments or not result.strokes:
        return None
    seg = result.segments[-1]
    stroke = result.strokes[-1]
    seg_dir = pick(lang, "向上" if seg.direction == "up" else "向下",
                    "an upward" if seg.direction == "up" else "a downward")
    stroke_dir = pick(lang, "向上" if stroke.direction == "up" else "向下",
                        "an upward" if stroke.direction == "up" else "a downward")

    parts = [pick(lang, f"当前处于{seg_dir}线段中的一根{stroke_dir}笔",
                  f"Currently riding {stroke_dir} stroke within {seg_dir} segment")]

    position = _price_position_clause(result, lang)
    if position:
        parts.append(position)

    if result.signals:
        last = result.signals[-1]
        suffix = pick(lang, "（候选）", " (candidate)") if not last.confirmed else ""
        parts.append(pick(lang, f"最近出现{last.label}{suffix}", f"recently showing {last.label}{suffix}"))

    return pick(lang, "，", ", ").join(parts) + pick(lang, "。", ".")
