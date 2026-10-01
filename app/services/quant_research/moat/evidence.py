"""财务证据：多年 ROIC（金融股用 ROE）与资金成本的差（超额回报）。纯函数。

Morningstar 把护城河定义为「超额回报（ROIC > WACC）能维持多久」：窄 ≥ 10 年、宽大概率 ≥ 20 年。
我们只有过去 10 年的报表，用「过去多少年持续跑赢资金成本」作为能否持续的证据。
资金成本用 CAPM 估算：股权成本 = 无风险利率 + β × 股权风险溢价（限制在 6% ~ 14%），
债务成本 = (无风险利率 + 1.5%) × (1 − 21%)，按市值与负债加权。
金融股（银行 / 保险）的投入资本口径不可比，改用 ROE 对比股权成本。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

RISK_FREE = 0.043
EQUITY_PREMIUM = 0.05
DEBT_SPREAD = 0.015
TAX = 0.21
COST_OF_EQUITY_RANGE = (0.06, 0.14)
STRONG_MIN_YEARS = 8
STRONG_MIN_SPREAD = 0.03     # 校准：5% 会把 KO 这类老牌消费品判成窄
MODERATE_MIN_YEARS = 5
MODERATE_ABOVE_SHARE = 0.7
TREND_BAND = 0.02            # 近 3 年与最早 3 年的平均超额相差超过 2 个百分点才算扩大 / 收窄

Level = Literal["strong", "moderate", "weak"]
Trend = Literal["widening", "stable", "narrowing"]


@dataclass(frozen=True)
class Evidence:
    metric: Literal["roic", "roe"]
    years: list[tuple[int, float]]     # (财年, 回报率)，新 → 旧
    cost_of_capital: float
    years_above: int
    n_years: int
    avg_spread: float | None
    trend_value: float | None
    trend: Trend | None
    level: Level
    beta: float

    @property
    def wacc(self) -> float:
        return self.cost_of_capital

    def to_dict(self) -> dict:
        d = asdict(self)
        d["years"] = [[y, r] for y, r in self.years]
        return d


def cost_of_capital(beta: float, market_cap: float, total_debt: float, *, financial: bool) -> float:
    """CAPM 股权成本与税后债务成本按市值 / 负债加权；金融股只用股权成本。"""
    lo, hi = COST_OF_EQUITY_RANGE
    ke = min(max(RISK_FREE + beta * EQUITY_PREMIUM, lo), hi)
    if financial:
        return ke
    kd = (RISK_FREE + DEBT_SPREAD) * (1 - TAX)
    total = market_cap + total_debt
    return (market_cap * ke + total_debt * kd) / total if total > 0 else ke


def compute_evidence(years: list[tuple[int, float]], *, beta: float | None, market_cap: float | None,
                     total_debt: float | None, financial: bool = False) -> Evidence:
    """years：(财年, ROIC 或 ROE)，任意顺序；内部按新 → 旧排列。"""
    ys = sorted(years, reverse=True)
    b = beta if beta is not None else 1.0
    coc = cost_of_capital(b, market_cap or 0.0, total_debt or 0.0, financial=financial)
    spreads = [r - coc for _, r in ys]
    n = len(spreads)
    above = sum(s > 0 for s in spreads)
    avg = sum(spreads) / n if n else None
    trend_value = (sum(spreads[:3]) / 3 - sum(spreads[-3:]) / 3) if n >= 6 else None
    trend: Trend | None = None
    if trend_value is not None:
        trend = "widening" if trend_value > TREND_BAND else "narrowing" if trend_value < -TREND_BAND else "stable"
    if n >= STRONG_MIN_YEARS and above >= n - 1 and (avg or 0) >= STRONG_MIN_SPREAD:
        level: Level = "strong"
    elif n >= MODERATE_MIN_YEARS and above >= MODERATE_ABOVE_SHARE * n and (avg or 0) > 0:
        level = "moderate"
    else:
        level = "weak"
    return Evidence("roe" if financial else "roic", ys, round(coc, 6), above, n,
                    round(avg, 6) if avg is not None else None,
                    round(trend_value, 6) if trend_value is not None else None, trend, level, b)
