"""公司所处阶段：Dickinson (2011) 现金流生命周期分类。只做标注，不改分数。

按最近 12 个月经营 / 投资 / 筹资现金流的正负：
初创 (− − +)、成长 (+ − +)、成熟 (+ − −)、收缩 (− + ±)，其余为调整期。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.quant_research.inputs import StockInputs, ttm

STAGE_NAMES: dict[str, tuple[str, str]] = {
    "intro": ("初创期", "Introduction"),
    "growth": ("成长期", "Growth"),
    "mature": ("成熟期", "Mature"),
    "shakeout": ("调整期", "Shake-out"),
    "decline": ("收缩期", "Contraction"),
}
_RULES = {
    ("-", "-", "+"): "intro",
    ("+", "-", "+"): "growth",
    ("+", "-", "-"): "mature",
    ("-", "+", "+"): "decline",
    ("-", "+", "-"): "decline",
}


def classify_stage(cfo: float | None, cfi: float | None, cff: float | None) -> str | None:
    """三项现金流符号 → 阶段键；任一缺失返回 None。"""
    if cfo is None or cfi is None or cff is None:
        return None

    def sign(x: float) -> str:
        return "+" if x > 0 else "-"

    return _RULES.get((sign(cfo), sign(cfi), sign(cff)), "shakeout")


@dataclass(frozen=True)
class StageInfo:
    key: str
    unprofitable: bool
    operating: float
    investing: float
    financing: float


def stage_of(inp: StockInputs) -> StageInfo | None:
    """金融股不标注：银行现金流由存贷款驱动，经营现金流为负是常态（Dickinson 原文也排除金融业）。"""
    if inp.sector_key == "financials":
        return None
    cf = inp.quarters_cash
    cfo = ttm(cf, "netCashProvidedByOperatingActivities")
    cfi = ttm(cf, "netCashProvidedByInvestingActivities")
    cff = ttm(cf, "netCashProvidedByFinancingActivities")
    key = classify_stage(cfo, cfi, cff)
    if key is None:
        return None
    eps = ttm(inp.quarters_income, "epsDiluted")
    return StageInfo(key, eps is not None and eps <= 0, cfo, cfi, cff)  # type: ignore[arg-type]
