"""公司所处阶段：营收增速为主轴、经营现金流为辅。决定综合分里各维度的权重（见 STAGE_WEIGHTS）。

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
from app.services.quant_research.metrics import DIMENSIONS

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
# 滞回：上期已在某阶段时，营收同比越过门槛不到这个幅度仍沿用旧阶段（阶段一换，整套权重跟着换，综合分会跳）
STAGE_HYSTERESIS = 0.02

# 综合分里各维度的权重（每行和为 1）。依据：成长期看增速、成熟期看估值与赚钱能力、收缩期看估值安全垫；
# None = 没有阶段（金融股等）→ 等权。改权重须升 METHODOLOGY_VERSION，并同步 methodology.py 与 iOS 推导文案。
STAGE_WEIGHTS: dict[str | None, dict[str, float]] = {
    "intro":    {"valuation": 0.10, "growth": 0.40, "profitability": 0.10, "momentum": 0.25, "revisions": 0.15},
    "growth":   {"valuation": 0.15, "growth": 0.35, "profitability": 0.20, "momentum": 0.20, "revisions": 0.10},
    "mature":   {"valuation": 0.30, "growth": 0.10, "profitability": 0.30, "momentum": 0.15, "revisions": 0.15},
    "shakeout": {"valuation": 0.30, "growth": 0.10, "profitability": 0.30, "momentum": 0.15, "revisions": 0.15},
    "decline":  {"valuation": 0.35, "growth": 0.05, "profitability": 0.35, "momentum": 0.15, "revisions": 0.10},
    None:       {d: 1 / len(DIMENSIONS) for d in DIMENSIONS},
}


def weights_for(stage: str | None) -> dict[str, float]:
    """阶段 → 维度权重；没有阶段或阶段未知 → 等权。"""
    return STAGE_WEIGHTS.get(stage, STAGE_WEIGHTS[None])


def classify_stage(cfo: float | None, g1: float | None, g3: float | None, prev: str | None = None) -> str | None:
    """经营现金流 + 营收同比 + 3 年复合增速 → 阶段键；经营现金流或同比缺失返回 None。

    prev = 上期阶段，用于滞回：成长 / 初创期的同比降到门槛下 2 个点内仍算高增长；收缩期同理（只放宽「留下」）。
    """
    if cfo is None or g1 is None:
        return None
    growth_min = GROWTH_YOY_MIN - STAGE_HYSTERESIS if prev in ("growth", "intro") else GROWTH_YOY_MIN
    shrink_max = SHRINK_YOY_MAX + STAGE_HYSTERESIS if prev == "decline" else SHRINK_YOY_MAX
    if g1 >= growth_min and (g3 is None or g3 >= GROWTH_CAGR3_MIN):
        return "growth" if cfo > 0 else "intro"
    if g1 <= shrink_max:
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


def stage_of(inp: StockInputs, rev_yoy: float | None, rev_cagr3: float | None,
             prev: str | None = None) -> StageInfo | None:
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
        key = classify_stage(cfo, rev_yoy, rev_cagr3, prev)
    if key is None:
        return None
    eps = ttm(inp.quarters_income, "epsDiluted")
    return StageInfo(key, eps is not None and eps <= 0, cfo, cfi, cff, rev_yoy, rev_cagr3)
