"""一只股票的原始输入：报表季度序列、分析师一致预期、收盘价。纯函数解析，无 IO。

FMP 的 fiscalYear 按财年归属标注（NVDA 截至 2026-07 的季度记为 fiscalYear=2027 Q2），
「上一完整财年实际值」按 fiscalYear 分组、凑齐 Q1~Q4 才算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class StockInputs:
    symbol: str
    as_of: date
    sector_key: str
    name: str | None = None
    price: float | None = None
    price_date: str | None = None
    closes: list[float] = field(default_factory=list)          # 升序（旧 → 新）
    quarters_income: list[dict] = field(default_factory=list)  # 新 → 旧
    quarters_cash: list[dict] = field(default_factory=list)    # 新 → 旧
    balance: dict | None = None                                # 最新一季
    estimates: list[dict] = field(default_factory=list)        # 按财年截止日升序
    shares_diluted: float | None = None

    @property
    def fy1(self) -> dict | None:
        return forward_entries(self.estimates, self.as_of)[0]

    @property
    def fy2(self) -> dict | None:
        return forward_entries(self.estimates, self.as_of)[1]

    @property
    def fiscal_period(self) -> str | None:
        """最新财报期，如「FY27 Q2」。"""
        if not self.quarters_income:
            return None
        q = self.quarters_income[0]
        fy = str(q.get("fiscalYear") or "")[-2:]
        return f"FY{fy} {q.get('period')}" if fy else None

    @property
    def filing_date(self) -> str | None:
        if not self.quarters_income:
            return None
        return (self.quarters_income[0].get("filingDate") or "")[:10] or None


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ttm(quarters: list[dict], key: str, offset: int = 0) -> float | None:
    """从 offset 起连续 4 季求和；不足 4 季或任一缺失返回 None。"""
    window = quarters[offset: offset + 4]
    if len(window) < 4:
        return None
    vals = [_num(q.get(key)) for q in window]
    if any(v is None for v in vals):
        return None
    return float(sum(vals))  # type: ignore[arg-type]


def fiscal_year_actual(quarters: list[dict], key: str) -> tuple[str, float] | None:
    """最近一个凑齐 Q1~Q4 的财年的实际值合计。"""
    by_year: dict[str, dict[str, float | None]] = {}
    for q in quarters:
        fy, period = str(q.get("fiscalYear") or ""), q.get("period")
        if fy and period in ("Q1", "Q2", "Q3", "Q4"):
            by_year.setdefault(fy, {})[period] = _num(q.get(key))
    for fy in sorted(by_year, reverse=True):
        periods = by_year[fy]
        if len(periods) == 4 and all(v is not None for v in periods.values()):
            return fy, float(sum(periods.values()))  # type: ignore[arg-type]
    return None


def forward_entries(estimates: list[dict], as_of: date) -> tuple[dict | None, dict | None]:
    """财年截止日在 as_of 之后的前两条一致预期（FY1、FY2）。"""
    iso = as_of.isoformat()
    fut = [e for e in estimates if str(e.get("date", "")) > iso]
    fut.sort(key=lambda e: e["date"])
    return (fut[0] if fut else None), (fut[1] if len(fut) > 1 else None)


def ntm(fy1: dict | None, fy2: dict | None, key: str, as_of: date) -> float | None:
    """未来 12 个月口径：按 FY1 剩余天数占一年的比例，对 FY1 / FY2 加权。"""
    if fy1 is None or _num(fy1.get(key)) is None:
        return None
    v1 = float(fy1[key])
    if fy2 is None or _num(fy2.get(key)) is None:
        return v1
    remaining = (date.fromisoformat(str(fy1["date"])[:10]) - as_of).days
    w = min(max(remaining / 365, 0.0), 1.0)
    return w * v1 + (1 - w) * float(fy2[key])


def analyst_count(fy1: dict | None) -> int:
    """FY1 覆盖的分析师人数（缺失为 0）。"""
    if not fy1:
        return 0
    return int(fy1.get("numAnalystsEps") or 0)


def build_inputs(*, symbol: str, as_of: date, sector_key: str, income: list | None, cash: list | None,
                 balance: list | dict | None, estimates: list | None, prices: list | None,
                 name: str | None = None) -> StockInputs:
    """把 FMP 原始响应整理成 StockInputs（排序、取最新值）。"""
    inc = sorted([q for q in (income or []) if isinstance(q, dict)], key=lambda q: q.get("date", ""), reverse=True)
    cf = sorted([q for q in (cash or []) if isinstance(q, dict)], key=lambda q: q.get("date", ""), reverse=True)
    if isinstance(balance, list):
        balance = max(balance, key=lambda q: q.get("date", "")) if balance else None
    est = sorted([e for e in (estimates or []) if isinstance(e, dict) and e.get("date")], key=lambda e: e["date"])
    px = sorted([p for p in (prices or []) if isinstance(p, dict) and _num(p.get("price")) is not None],
                key=lambda p: p["date"])
    closes = [float(p["price"]) for p in px]
    shares = _num(inc[0].get("weightedAverageShsOutDil")) if inc else None
    return StockInputs(
        symbol=symbol.upper(), as_of=as_of, sector_key=sector_key, name=name,
        price=closes[-1] if closes else None, price_date=px[-1]["date"] if px else None,
        closes=closes, quarters_income=inc, quarters_cash=cf, balance=balance,
        estimates=est, shares_diluted=shares,
    )
