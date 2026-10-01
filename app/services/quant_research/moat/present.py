"""把存档的护城河评估组装成接口响应（中 / 英大白话）。纯函数。"""

from __future__ import annotations

from typing import Literal

from app.schemas.quant_research import MoatEvidenceOut, MoatOut, MoatSourceOut, MoatYear

Lang = Literal["zh", "en"]

RATING_NAMES = {"wide": ("宽护城河", "Wide moat"), "narrow": ("窄护城河", "Narrow moat"),
                "none": ("无护城河", "No moat")}
TREND_NAMES = {"widening": ("超额回报在扩大", "Excess returns widening"),
               "stable": ("超额回报稳定", "Excess returns stable"),
               "narrowing": ("超额回报在收窄", "Excess returns narrowing")}
SOURCE_NAMES = {"intangible_assets": ("无形资产", "Intangible assets"),
                "switching_costs": ("转换成本", "Switching costs"),
                "network_effect": ("网络效应", "Network effect"),
                "cost_advantage": ("成本优势", "Cost advantage"),
                "efficient_scale": ("有效规模", "Efficient scale")}
STRENGTH_NAMES = {"strong": ("强", "Strong"), "moderate": ("中", "Moderate"), "weak": ("弱", "Weak"),
                  "none": ("无", "None")}
LEVEL_NAMES = {"strong": ("财务证据强", "Strong financial evidence"),
               "moderate": ("财务证据一般", "Moderate financial evidence"),
               "weak": ("财务证据弱", "Weak financial evidence")}
METHOD_NOTE = (
    "参照 Morningstar 护城河框架：先看过去约 10 年回报率是否持续高于资金成本（财务证据），再由模型读最新年报业务章节，"
    "判断无形资产、转换成本、网络效应、成本优势、有效规模五种来源，每条判断都附年报原文。两者同时成立才算有护城河。"
    "只展示，不计入综合等级。",
    "Follows the Morningstar moat framework: first, whether returns have stayed above the cost of capital for about "
    "10 years (financial evidence); then a model reads the business section of the latest annual report to judge five "
    "sources — intangible assets, switching costs, network effect, cost advantage and efficient scale — each backed by "
    "quotes from the report. A moat requires both. Shown only, not part of the composite grade.",
)


def _i(lang: Lang, pair: tuple[str, str]) -> str:
    return pair[0] if lang == "zh" else pair[1]


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def evidence_text(ev: dict, lang: Lang) -> str:
    """一句话证据，如「过去 10 年里 9 年 ROIC 高于资金成本（约 7.9%），平均高出 12.1 个百分点」。"""
    n, above, avg, coc = ev["n_years"], ev["years_above"], ev.get("avg_spread"), ev["cost_of_capital"]
    if n == 0:
        return _i(lang, ("缺少历年回报率数据", "No multi-year return data"))
    roe = ev["metric"] == "roe"
    if lang == "zh":
        metric, cost = ("ROE", "股权资金成本") if roe else ("ROIC", "资金成本")
        head = f"过去 {n} 年里 {above} 年 {metric} 高于{cost}（约 {_pct(coc)}）"
        if avg is None:
            return head
        word = "高出" if avg >= 0 else "低于"
        return f"{head}，平均{word} {abs(avg) * 100:.1f} 个百分点"
    metric, cost = ("ROE", "cost of equity") if roe else ("ROIC", "cost of capital")
    head = f"{metric} beat the {cost} (about {_pct(coc)}) in {above} of the last {n} years"
    if avg is None:
        return head
    word = "above" if avg >= 0 else "below"
    return f"{head}, by an average of {abs(avg) * 100:.1f} points {word}"


def moat_out(row: object, lang: Lang) -> MoatOut:
    """row：QuantMoatAssessment。"""
    ev: dict = row.evidence  # type: ignore[attr-defined]
    rating: str = row.rating  # type: ignore[attr-defined]
    trend: str | None = row.trend  # type: ignore[attr-defined]
    metric = ev["metric"]
    evidence = MoatEvidenceOut(
        metric=metric,
        metric_name=_i(lang, ("净资产收益率 ROE", "Return on equity (ROE)") if metric == "roe"
                       else ("投入资本回报率 ROIC", "Return on invested capital (ROIC)")),
        years=[MoatYear(year=y, value=v) for y, v in ev["years"]],
        cost_of_capital=ev["cost_of_capital"], years_above=ev["years_above"], n_years=ev["n_years"],
        avg_spread=ev.get("avg_spread"), level=ev["level"], level_name=_i(lang, LEVEL_NAMES[ev["level"]]),
        text=evidence_text(ev, lang),
    )
    sources = [MoatSourceOut(
        key=s["source"], name=_i(lang, SOURCE_NAMES[s["source"]]), strength=s["strength"],
        strength_name=_i(lang, STRENGTH_NAMES[s["strength"]]),
        reason=s["reason_zh"] if lang == "zh" else s["reason_en"], quotes=s.get("quotes", []),
    ) for s in row.sources]  # type: ignore[attr-defined]
    strong = [s.name for s in sorted(sources, key=lambda x: ("strong", "moderate", "weak", "none").index(x.strength))
              if s.strength in ("strong", "moderate")]
    sep = "、" if lang == "zh" else ", "
    if strong:
        summary = _i(lang, (f"主要来源：{sep.join(strong)}", f"Main sources: {sep.join(strong)}"))
    else:
        summary = _i(lang, ("年报中没有找到可核实的护城河来源", "No verifiable moat source found in the annual report"))
    threats: dict = row.threats  # type: ignore[attr-defined]
    return MoatOut(
        status="ok", rating=rating, rating_name=_i(lang, RATING_NAMES[rating]),  # type: ignore[arg-type]
        trend=trend, trend_name=_i(lang, TREND_NAMES[trend]) if trend else None,  # type: ignore[arg-type]
        summary=summary, evidence=evidence, sources=sources,
        threats=threats.get(lang) or threats.get("zh"),
        filed_date=row.filed_date, tenk_url=row.tenk_url,  # type: ignore[attr-defined]
        method_note=_i(lang, METHOD_NOTE),
    )


def moat_placeholder(lang: Lang, *, in_universe: bool) -> MoatOut:
    """还没有评估结果：样本内为「评估中」，样本外为「暂未覆盖」。"""
    if in_universe:
        return MoatOut(status="pending", method_note=_i(lang, METHOD_NOTE), status_note=_i(lang, (
            "护城河评估中：需要读完最新年报，通常在部署或新年报披露后数小时内完成",
            "Moat assessment in progress: it reads the latest annual report and usually completes within hours")))
    return MoatOut(status="not_covered", method_note=_i(lang, METHOD_NOTE), status_note=_i(lang, (
        "护城河评估暂只覆盖标普1500 成分股", "Moat assessments currently cover S&P 1500 constituents only")))
