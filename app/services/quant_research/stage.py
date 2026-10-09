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

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

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
# 综合分里各维度的权重（每行和为 1）。依据：成长期看增速、成熟期看估值与赚钱能力、初创 / 调整 / 收缩期更看重偿债与现金能撑多久；
# None = 没有阶段（金融股等）→ 等权。改权重须升 METHODOLOGY_VERSION，并同步 methodology.py 与 iOS 推导文案。
STAGE_WEIGHTS: dict[str | None, dict[str, float]] = {
    "intro":    {"valuation": 0.08, "growth": 0.32, "profitability": 0.08, "momentum": 0.20, "revisions": 0.12,
                 "stability": 0.20},
    "growth":   {"valuation": 0.12, "growth": 0.30, "profitability": 0.18, "momentum": 0.15, "revisions": 0.10,
                 "stability": 0.15},
    "mature":   {"valuation": 0.25, "growth": 0.08, "profitability": 0.25, "momentum": 0.12, "revisions": 0.12,
                 "stability": 0.18},
    "shakeout": {"valuation": 0.22, "growth": 0.08, "profitability": 0.25, "momentum": 0.10, "revisions": 0.10,
                 "stability": 0.25},
    "decline":  {"valuation": 0.28, "growth": 0.04, "profitability": 0.28, "momentum": 0.10, "revisions": 0.05,
                 "stability": 0.25},
    None:       {d: 1 / len(DIMENSIONS) for d in DIMENSIONS},
}


# 估值维度里各倍数在不同阶段的**相对权重**（只改权重，不改比较对象：百分位仍和整个行业比，保证行业维度可比；
# 这和 STAGE_WEIGHTS 一样按增速 × 现金流连续插值）。思路：
# - 成熟期：保持原来的 14 项等权，不动。
# - 成长期（高增长 + 造血）：看前瞻（预期增长兑现后才贵不贵）、PEG、营收倍数与市现率；过往市盈率 / EV·EBIT 减半或不看，市净率没有意义。
# - 初创期（高增长 + 烧钱）：利润为负，市盈率 / PEG / EV·利润倍数 / 市现率全是「无意义」（会被当成最差），只看营收类倍数，市净率作辅助。
# - 调整期：看盈利与资产类（市盈率、EV/EBITDA、EV/EBIT、市净率、市现率），营收类减半，PEG 不看（增速不可靠）。
# - 收缩期：预期不可靠，不看前瞻与 PEG；看资产与现金类（市净率、EV/EBITDA、市现率）。
VALUATION_KEYS: tuple[str, ...] = ("pe_ttm", "pe_fwd", "peg_ttm", "peg_fwd", "ps_ttm", "ps_fwd", "ev_sales_ttm", "ev_sales_fwd",
                                   "ev_ebitda_ttm", "ev_ebitda_fwd", "ev_ebit_ttm", "ev_ebit_fwd", "pb", "pcf")


def _vrow(**w: float) -> dict[str, float]:
    return {k: float(w.get(k, 0.0)) for k in VALUATION_KEYS}


VALUATION_WEIGHTS: dict[str, dict[str, float]] = {
    "mature":   {k: 1.0 for k in VALUATION_KEYS},
    "growth":   _vrow(pe_ttm=0.5, pe_fwd=1, peg_ttm=0.5, peg_fwd=1, ps_ttm=1, ps_fwd=1, ev_sales_ttm=1, ev_sales_fwd=1,
                      ev_ebitda_ttm=0.5, ev_ebitda_fwd=0.5, ev_ebit_ttm=0, ev_ebit_fwd=0.5, pb=0, pcf=1),
    "intro":    _vrow(ps_ttm=1, ps_fwd=1, ev_sales_ttm=1, ev_sales_fwd=1, pb=0.5),
    "shakeout": _vrow(pe_ttm=1, pe_fwd=0.5, ps_ttm=0.5, ps_fwd=0.5, ev_sales_ttm=0.5, ev_sales_fwd=0.5,
                      ev_ebitda_ttm=1, ev_ebitda_fwd=0.5, ev_ebit_ttm=1, ev_ebit_fwd=0.5, pb=1, pcf=1),
    "decline":  _vrow(pe_ttm=0.5, ps_ttm=0.5, ev_sales_ttm=0.5, ev_ebitda_ttm=1, ev_ebit_ttm=0.5, pb=1.5, pcf=1),
}



def weights_for(stage: str | None) -> dict[str, float]:
    """阶段 → 该阶段的**基准权重行**；没有阶段或阶段未知 → 等权。实际综合分用的是连续插值后的 blend_weights。"""
    return STAGE_WEIGHTS.get(stage, STAGE_WEIGHTS[None])


# 权重按「营收增速 × 现金流利润率」连续插值，不再在阶段门槛处整行跳变（14.9% 与 15.1% 的公司权重差一整行不合理）。
# 各过渡区以原阶段门槛为中心，在两侧各延伸 5 个百分点；远离门槛时与上表对应行完全一致。
GROWTH_RAMP = (0.10, 0.20)     # 高增长：营收同比 10% → 20%（中心 = 门槛 15%）
SHRINK_RAMP = (0.0, 0.10)      # 萎缩：营收同比 0% → −10%，按 −同比 计（中心 = 门槛 −5%）
CAGR_RAMP = (0.05, 0.15)       # 3 年复合不足会给高增长打折：5% → 15%（中心 = 门槛 10%）
CASH_RAMP = (-0.05, 0.05)      # 经营现金流占营收：−5% → +5%（0 = 正负各半）


def _ramp(x: float, lo: float, hi: float) -> float:
    return min(max((x - lo) / (hi - lo), 0.0), 1.0)


def _blend(rows: Mapping[Any, Mapping[str, float]], keys: Iterable[str], g1: float, g3: float | None, cfo_margin: float) -> dict[str, float]:
    """在 rows 的五行（成长 / 成熟 / 调整 / 初创 / 收缩）之间按增速轴 × 现金轴双向线性插值。"""
    hi = _ramp(g1, *GROWTH_RAMP)
    if g3 is not None:
        hi = min(hi, _ramp(g3, *CAGR_RAMP))
    sh = _ramp(-g1, *SHRINK_RAMP)
    mid = 1.0 - hi - sh
    cash = _ramp(cfo_margin, *CASH_RAMP)
    pos = (hi, rows["growth"]), (mid, rows["mature"]), (sh, rows["shakeout"])
    neg = (hi, rows["intro"]), (mid, rows["shakeout"]), (sh, rows["decline"])
    return {k: cash * sum(w * row[k] for w, row in pos) + (1 - cash) * sum(w * row[k] for w, row in neg) for k in keys}


def blend_weights(g1: float, g3: float | None, cfo_margin: float) -> dict[str, float]:
    """营收同比 g1 / 3 年复合 g3 / 经营现金流占营收 cfo_margin → 连续插值的维度权重（和为 1）。

    增速轴：萎缩 ↔ 平稳 ↔ 高增长；现金轴：烧钱 ↔ 造血。六个角就是 STAGE_WEIGHTS 的五行
    （造血：调整 / 成熟 / 成长，烧钱：收缩 / 调整 / 初创）。
    """
    return _blend(STAGE_WEIGHTS, DIMENSIONS, g1, g3, cfo_margin)


def blend_valuation_weights(g1: float, g3: float | None, cfo_margin: float) -> dict[str, float]:
    """同一套插值，用于估值维度里 14 个倍数的指标权重（相对权重，不归一）。"""
    return _blend(VALUATION_WEIGHTS, VALUATION_KEYS, g1, g3, cfo_margin)


def classify_stage(cfo: float | None, g1: float | None, g3: float | None) -> str | None:
    """经营现金流 + 营收同比 + 3 年复合增速 → 阶段键（界面上的阶段标签）；经营现金流或同比缺失返回 None。

    标签只用于展示；综合分的权重由 blend_weights 连续插值，不在标签切换处跳变。
    """
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
    weights: dict[str, float]    # 综合分里各维度的权重（连续插值后，和为 1）
    valuation_weights: dict[str, float]    # 估值维度里各倍数的相对权重（连续插值后）


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
        # 营收基数为零（尚无收入）且在烧钱：整行按初创期
        key = "intro" if cfo <= 0 else None
        weights, val_weights = STAGE_WEIGHTS["intro"], VALUATION_WEIGHTS["intro"]
    else:
        key = classify_stage(cfo, rev_yoy, rev_cagr3)
        rev = ttm(inp.quarters_income, "revenue")
        cfo_margin = cfo / rev if (rev is not None and rev > 0) else (1.0 if cfo > 0 else -1.0)
        if rev_yoy is not None:
            weights = blend_weights(rev_yoy, rev_cagr3, cfo_margin)
            val_weights = blend_valuation_weights(rev_yoy, rev_cagr3, cfo_margin)
        else:
            weights, val_weights = STAGE_WEIGHTS[None], VALUATION_WEIGHTS["mature"]
    if key is None:
        return None
    eps = ttm(inp.quarters_income, "epsDiluted")
    return StageInfo(key, eps is not None and eps <= 0, cfo, cfi, cff, rev_yoy, rev_cagr3, weights, val_weights)
