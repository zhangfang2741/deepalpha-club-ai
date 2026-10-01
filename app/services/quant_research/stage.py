"""公司所处阶段：营收增速为主轴、经营现金流为辅。只做标注，不改分数。

思路取自 Morningstar 股票类型（源自彼得·林奇的公司分类），映射到五阶段：
投机成长 → 初创、激进 / 经典成长 → 成长、缓慢成长 / 高股息 → 成熟、困境 → 收缩，其余为调整期。

- 高增长 = 营收同比 ≥ 15%，且 3 年复合增速 ≥ 10%（不足 3 年历史只看同比；挡周期性反弹，如停产后复产）
  - 经营现金流 > 0 → 成长期；≤ 0 → 初创期
- 营收萎缩 = 同比 ≤ −5%：经营现金流 > 0 → 调整期；≤ 0 → 收缩期
- 其余：经营现金流 > 0 → 成熟期；≤ 0 → 调整期
- 营收基数为零（尚无收入）且经营现金流 ≤ 0 → 初创期

不再用 Dickinson (2011) 三项现金流符号法：美股筹资现金流主要反映回购 / 分红 / RSU 代扣税，
与生命周期无关——实测 NVDA、AVGO、FIG 等高增长公司被判成熟期，借债扩建的公用事业被判成长期。
iOS 的判定规则文案（QuantLifecycleStage.rule）与这里的门槛由 test_stage.py::test_stage_ios_rules_match_thresholds 对齐守护。
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
GROWTH_YOY_MIN = 0.15
GROWTH_CAGR3_MIN = 0.10
SHRINK_YOY_MAX = -0.05


def classify_stage(cfo: float | None, g1: float | None, g3: float | None) -> str | None:
    """经营现金流 + 营收同比 + 3 年复合增速 → 阶段键；经营现金流或同比缺失返回 None。"""
    if cfo is None or g1 is None:
        return None
    if g1 >= GROWTH_YOY_MIN and (g3 is None or g3 >= GROWTH_CAGR3_MIN):
        return "growth" if cfo > 0 else "intro"
    if g1 <= SHRINK_YOY_MAX:
        return "shakeout" if cfo > 0 else "decline"
    return "mature" if cfo > 0 else "shakeout"


@dataclass(frozen=True)
class StageInfo:
    key: str
    unprofitable: bool
    operating: float
    investing: float
    financing: float
    revenue_growth: float | None
    revenue_cagr_3y: float | None


def stage_of(inp: StockInputs, rev_yoy: float | None, rev_cagr3: float | None) -> StageInfo | None:
    """rev_yoy / rev_cagr3 取成长维度同名指标，保证与页面上的增速一致。

    金融股不标注：银行营收与现金流由存贷款驱动，口径不可比。
    """
    if inp.sector_key == "financials":
        return None
    cf = inp.quarters_cash
    cfo = ttm(cf, "netCashProvidedByOperatingActivities")
    cfi = ttm(cf, "netCashProvidedByInvestingActivities")
    cff = ttm(cf, "netCashProvidedByFinancingActivities")
    if cfo is None or cfi is None or cff is None:
        return None
    rev_prev = ttm(inp.quarters_income, "revenue", 4)
    if rev_yoy is None and rev_prev is not None and rev_prev <= 0:
        key = "intro" if cfo <= 0 else None
    else:
        key = classify_stage(cfo, rev_yoy, rev_cagr3)
    if key is None:
        return None
    eps = ttm(inp.quarters_income, "epsDiluted")
    return StageInfo(key, eps is not None and eps <= 0, cfo, cfi, cff, rev_yoy, rev_cagr3)
