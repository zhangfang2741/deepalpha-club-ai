"""指标注册表与计算。

全部用报表原始值自己算（不用第三方预算好的比率），每个指标都带着
算式输入，文案层能写出「股价 227.21 ÷ NTM EPS 预期 5.51 = 41.2」。

特殊值状态（见设计 §3.2）：
- not_meaningful：分母为负且确属「没有利润」（亏损导致 PE 为负等）→ 打分时按最差计。
- not_applicable：数值无意义但不代表经营不佳（回购导致股东权益为负时的 P/B、ROE）→ 不参与。
- missing：数据缺失或增长基数 ≤ 0 → 不参与。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.quant_research.inputs import (
    StockInputs,
    analyst_count,
    fiscal_year_actual,
    ntm,
    ttm,
)

Status = Literal["ok", "not_meaningful", "not_applicable", "missing", "insufficient_sample"]
Direction = Literal["lower_better", "higher_better"]
DIMENSIONS: list[str] = ["valuation", "growth", "profitability", "momentum", "revisions"]
DIMENSION_NAMES: dict[str, tuple[str, str]] = {
    "valuation": ("估值", "Valuation"),
    "growth": ("成长", "Growth"),
    "profitability": ("盈利能力", "Profitability"),
    "momentum": ("动量", "Momentum"),
    "revisions": ("EPS 修正", "EPS Revisions"),
}
MIN_ANALYSTS = 3
MOMENTUM_WINDOWS = {"r3m": 63, "r6m": 126, "r9m": 189, "r12m": 252}


@dataclass(frozen=True)
class MetricDef:
    key: str
    dimension: str
    group: str            # 页面折叠行，如「市盈率」
    group_en: str
    direction: Direction
    name_zh: str
    name_en: str
    desc_zh: str
    desc_en: str
    unit: Literal["x", "pct"]  # 倍数 / 百分比（显示用）


def _d(key: str, dim: str, group: str, group_en: str, direction: Direction, name_zh: str, name_en: str,
       desc_zh: str, desc_en: str, unit: Literal["x", "pct"] = "x") -> MetricDef:
    return MetricDef(key, dim, group, group_en, direction, name_zh, name_en, desc_zh, desc_en, unit)


_V, _G, _P, _M, _R = "valuation", "growth", "profitability", "momentum", "revisions"
_LO: Direction = "lower_better"
_HI: Direction = "higher_better"

METRICS: dict[str, MetricDef] = {m.key: m for m in [
    # 估值
    _d("pe_ttm", _V, "市盈率", "P/E", _LO, "市盈率 TTM", "P/E (TTM)",
       "股价相对最近 12 个月每股收益的倍数", "Price over trailing 12-month diluted EPS"),
    _d("pe_fwd", _V, "市盈率", "P/E", _LO, "前瞻市盈率", "P/E (FWD)",
       "股价相对分析师预期未来 12 个月每股收益的倍数", "Price over next-12-month consensus EPS"),
    _d("peg_ttm", _V, "PEG", "PEG", _LO, "PEG TTM", "PEG (TTM)",
       "市盈率 TTM 除以最近一年 EPS 增速（%）", "P/E (TTM) divided by trailing EPS growth (%)"),
    _d("peg_fwd", _V, "PEG", "PEG", _LO, "前瞻 PEG", "PEG (FWD)",
       "前瞻市盈率除以分析师预期的下一年 EPS 增速（%）", "P/E (FWD) divided by expected next-year EPS growth (%)"),
    _d("ps_ttm", _V, "市销率", "P/S", _LO, "市销率 TTM", "P/S (TTM)",
       "市值相对最近 12 个月营收的倍数", "Market cap over trailing 12-month revenue"),
    _d("ps_fwd", _V, "市销率", "P/S", _LO, "前瞻市销率", "P/S (FWD)",
       "市值相对分析师预期未来 12 个月营收的倍数", "Market cap over next-12-month consensus revenue"),
    _d("ev_sales_ttm", _V, "EV/营收", "EV/Sales", _LO, "EV/营收 TTM", "EV/Sales (TTM)",
       "企业价值（市值 + 负债 − 现金）相对最近 12 个月营收的倍数", "Enterprise value over trailing revenue"),
    _d("ev_sales_fwd", _V, "EV/营收", "EV/Sales", _LO, "前瞻 EV/营收", "EV/Sales (FWD)",
       "企业价值相对分析师预期未来 12 个月营收的倍数", "Enterprise value over next-12-month consensus revenue"),
    _d("ev_ebitda_ttm", _V, "EV/EBITDA", "EV/EBITDA", _LO, "EV/EBITDA TTM", "EV/EBITDA (TTM)",
       "企业价值相对最近 12 个月 EBITDA 的倍数", "Enterprise value over trailing EBITDA"),
    _d("ev_ebitda_fwd", _V, "EV/EBITDA", "EV/EBITDA", _LO, "前瞻 EV/EBITDA", "EV/EBITDA (FWD)",
       "企业价值相对分析师预期未来 12 个月 EBITDA 的倍数", "Enterprise value over next-12-month consensus EBITDA"),
    _d("ev_ebit_ttm", _V, "EV/EBIT", "EV/EBIT", _LO, "EV/EBIT TTM", "EV/EBIT (TTM)",
       "企业价值相对最近 12 个月 EBIT 的倍数", "Enterprise value over trailing EBIT"),
    _d("ev_ebit_fwd", _V, "EV/EBIT", "EV/EBIT", _LO, "前瞻 EV/EBIT", "EV/EBIT (FWD)",
       "企业价值相对分析师预期未来 12 个月 EBIT 的倍数", "Enterprise value over next-12-month consensus EBIT"),
    _d("pb", _V, "市净率", "P/B", _LO, "市净率", "P/B",
       "市值相对股东权益（账面净资产）的倍数", "Market cap over shareholders' equity"),
    _d("pcf", _V, "市现率", "P/CF", _LO, "市现率 TTM", "P/CF (TTM)",
       "市值相对最近 12 个月经营现金流的倍数", "Market cap over trailing operating cash flow"),
    # 成长
    _d("rev_yoy", _G, "营收", "Revenue", _HI, "营收同比", "Revenue YoY",
       "最近 12 个月营收相比上一个 12 个月的增速", "Trailing 12-month revenue vs the prior 12 months", "pct"),
    _d("rev_fwd", _G, "营收", "Revenue", _HI, "营收预期增速", "Revenue growth (FWD)",
       "分析师预期本财年营收相比上一完整财年实际值的增速", "Consensus current-FY revenue vs last full-year actual", "pct"),
    _d("rev_cagr3", _G, "营收", "Revenue", _HI, "营收 3 年复合增速", "Revenue 3Y CAGR",
       "最近 12 个月营收相比 3 年前同期的年化增速", "Annualized growth of trailing revenue over 3 years", "pct"),
    _d("ebitda_yoy", _G, "EBITDA", "EBITDA", _HI, "EBITDA 同比", "EBITDA YoY",
       "最近 12 个月 EBITDA 相比上一个 12 个月的增速", "Trailing EBITDA vs the prior 12 months", "pct"),
    _d("ebitda_fwd", _G, "EBITDA", "EBITDA", _HI, "EBITDA 预期增速", "EBITDA growth (FWD)",
       "分析师预期本财年 EBITDA 相比上一完整财年实际值的增速", "Consensus current-FY EBITDA vs last full-year actual", "pct"),
    _d("ebit_yoy", _G, "EBIT", "EBIT", _HI, "EBIT 同比", "EBIT YoY",
       "最近 12 个月 EBIT 相比上一个 12 个月的增速", "Trailing EBIT vs the prior 12 months", "pct"),
    _d("ebit_fwd", _G, "EBIT", "EBIT", _HI, "EBIT 预期增速", "EBIT growth (FWD)",
       "分析师预期本财年 EBIT 相比上一完整财年实际值的增速", "Consensus current-FY EBIT vs last full-year actual", "pct"),
    _d("eps_yoy", _G, "EPS", "EPS", _HI, "EPS 同比", "EPS YoY",
       "最近 12 个月稀释每股收益相比上一个 12 个月的增速", "Trailing diluted EPS vs the prior 12 months", "pct"),
    _d("eps_fwd", _G, "EPS", "EPS", _HI, "EPS 预期增速", "EPS growth (FWD)",
       "分析师预期本财年 EPS 相比上一完整财年实际值的增速", "Consensus current-FY EPS vs last full-year actual", "pct"),
    # 盈利能力
    _d("gross_m", _P, "毛利率", "Gross margin", _HI, "毛利率", "Gross margin",
       "最近 12 个月毛利占营收的比例", "Trailing gross profit over revenue", "pct"),
    _d("ebit_m", _P, "EBIT 利润率", "EBIT margin", _HI, "EBIT 利润率", "EBIT margin",
       "最近 12 个月 EBIT 占营收的比例", "Trailing EBIT over revenue", "pct"),
    _d("ebitda_m", _P, "EBITDA 利润率", "EBITDA margin", _HI, "EBITDA 利润率", "EBITDA margin",
       "最近 12 个月 EBITDA 占营收的比例", "Trailing EBITDA over revenue", "pct"),
    _d("net_m", _P, "净利率", "Net margin", _HI, "净利率", "Net margin",
       "最近 12 个月净利润占营收的比例", "Trailing net income over revenue", "pct"),
    _d("fcf_m", _P, "自由现金流利润率", "FCF margin", _HI, "自由现金流利润率", "FCF margin",
       "最近 12 个月自由现金流（经营现金流 − 资本开支）占营收的比例", "Trailing free cash flow over revenue", "pct"),
    _d("roe", _P, "ROE", "ROE", _HI, "ROE", "Return on equity",
       "最近 12 个月净利润相对股东权益的比例", "Trailing net income over shareholders' equity", "pct"),
    _d("roa", _P, "ROA", "ROA", _HI, "ROA", "Return on assets",
       "最近 12 个月净利润相对总资产的比例", "Trailing net income over total assets", "pct"),
    _d("roic", _P, "ROIC", "ROIC", _HI, "ROIC", "Return on invested capital",
       "税后 EBIT 相对投入资本（负债 + 股东权益 − 现金）的比例", "After-tax EBIT over debt + equity − cash", "pct"),
    _d("asset_turn", _P, "资产周转率", "Asset turnover", _HI, "资产周转率", "Asset turnover",
       "最近 12 个月营收相对总资产的倍数", "Trailing revenue over total assets", "pct"),
    # 动量
    _d("r3m", _M, "3 月", "3M", _HI, "3 个月涨幅", "3M price change",
       "最近 3 个月（63 个交易日）的前复权涨跌幅", "Dividend-adjusted price change over 63 trading days", "pct"),
    _d("r6m", _M, "6 月", "6M", _HI, "6 个月涨幅", "6M price change",
       "最近 6 个月（126 个交易日）的前复权涨跌幅", "Dividend-adjusted price change over 126 trading days", "pct"),
    _d("r9m", _M, "9 月", "9M", _HI, "9 个月涨幅", "9M price change",
       "最近 9 个月（189 个交易日）的前复权涨跌幅", "Dividend-adjusted price change over 189 trading days", "pct"),
    _d("r12m", _M, "12 月", "12M", _HI, "12 个月涨幅", "12M price change",
       "最近 12 个月（252 个交易日）的前复权涨跌幅", "Dividend-adjusted price change over 252 trading days", "pct"),
    # EPS 修正（计算见 revisions.py）
    _d("eps_fy1_30d", _R, "本财年 EPS", "FY1 EPS", _HI, "本财年 EPS 预期 30 天变化", "FY1 EPS revision (30D)",
       "分析师对本财年每股收益的一致预期，相比 30 天前的变化", "Change in FY1 consensus EPS vs 30 days ago", "pct"),
    _d("eps_fy1_90d", _R, "本财年 EPS", "FY1 EPS", _HI, "本财年 EPS 预期 90 天变化", "FY1 EPS revision (90D)",
       "分析师对本财年每股收益的一致预期，相比 90 天前的变化", "Change in FY1 consensus EPS vs 90 days ago", "pct"),
    _d("eps_fy2_90d", _R, "下财年 EPS", "FY2 EPS", _HI, "下财年 EPS 预期 90 天变化", "FY2 EPS revision (90D)",
       "分析师对下一财年每股收益的一致预期，相比 90 天前的变化", "Change in FY2 consensus EPS vs 90 days ago", "pct"),
    _d("rev_fy1_90d", _R, "本财年营收", "FY1 revenue", _HI, "本财年营收预期 90 天变化", "FY1 revenue revision (90D)",
       "分析师对本财年营收的一致预期，相比 90 天前的变化", "Change in FY1 consensus revenue vs 90 days ago", "pct"),
]}

# 算式输入的标签（zh, en）
INPUT_LABELS: dict[str, tuple[str, str]] = {
    "price": ("股价", "Price"), "market_cap": ("市值", "Market cap"), "ev": ("企业价值", "Enterprise value"),
    "eps_ttm": ("EPS TTM", "EPS (TTM)"), "eps_ttm_prev": ("上一个 12 个月 EPS", "Prior-12M EPS"),
    "eps_ntm": ("NTM EPS 预期", "NTM EPS est."), "eps_fy1": ("本财年 EPS 预期", "FY1 EPS est."),
    "eps_fy2": ("下财年 EPS 预期", "FY2 EPS est."), "eps_fy0": ("上一财年 EPS 实际", "Last-FY EPS"),
    "rev_ttm": ("营收 TTM", "Revenue (TTM)"), "rev_ttm_prev": ("上一个 12 个月营收", "Prior-12M revenue"),
    "rev_ttm_3y": ("3 年前同期营收", "Revenue 3Y ago"), "rev_ntm": ("NTM 营收预期", "NTM revenue est."),
    "rev_fy1": ("本财年营收预期", "FY1 revenue est."), "rev_fy0": ("上一财年营收实际", "Last-FY revenue"),
    "ebitda_ttm": ("EBITDA TTM", "EBITDA (TTM)"), "ebitda_ttm_prev": ("上一个 12 个月 EBITDA", "Prior-12M EBITDA"),
    "ebitda_ntm": ("NTM EBITDA 预期", "NTM EBITDA est."), "ebitda_fy1": ("本财年 EBITDA 预期", "FY1 EBITDA est."),
    "ebitda_fy0": ("上一财年 EBITDA 实际", "Last-FY EBITDA"),
    "ebit_ttm": ("EBIT TTM", "EBIT (TTM)"), "ebit_ttm_prev": ("上一个 12 个月 EBIT", "Prior-12M EBIT"),
    "ebit_ntm": ("NTM EBIT 预期", "NTM EBIT est."), "ebit_fy1": ("本财年 EBIT 预期", "FY1 EBIT est."),
    "ebit_fy0": ("上一财年 EBIT 实际", "Last-FY EBIT"),
    "gross_ttm": ("毛利 TTM", "Gross profit (TTM)"), "net_ttm": ("净利润 TTM", "Net income (TTM)"),
    "ocf_ttm": ("经营现金流 TTM", "Operating cash flow (TTM)"), "fcf_ttm": ("自由现金流 TTM", "Free cash flow (TTM)"),
    "equity": ("股东权益", "Shareholders' equity"), "assets": ("总资产", "Total assets"),
    "invested": ("投入资本", "Invested capital"), "nopat": ("税后 EBIT", "After-tax EBIT"),
    "pe": ("市盈率", "P/E"), "growth_pct": ("EPS 增速 %", "EPS growth %"),
    "close_now": ("最新收盘价", "Latest close"), "close_then": ("期初收盘价", "Starting close"),
    "est_new": ("当前一致预期", "Current consensus"), "est_old": ("当时一致预期", "Consensus then"),
}


Op = Literal["div", "growth", "cagr3", "ret", "peg", "change"]


@dataclass
class MetricValue:
    value: float | None
    status: Status
    inputs: list[tuple[str, float | None]] = field(default_factory=list)
    op: Op = "div"
    meta: dict = field(default_factory=dict)  # 如分析师人数、预期区间、时间点


def _missing(op: Op = "div", inputs: list | None = None) -> MetricValue:
    return MetricValue(None, "missing", inputs or [], op)


def _multiple(num: float | None, den: float | None, inputs, *, den_nonpositive: Status) -> MetricValue:
    if num is None or den is None:
        return _missing("div", inputs)
    if den <= 0:
        return MetricValue(None, den_nonpositive, inputs, "div")
    if num <= 0:
        return MetricValue(None, "not_applicable", inputs, "div")
    return MetricValue(num / den, "ok", inputs, "div")


def _ratio(num: float | None, den: float | None, inputs, *, den_nonpositive: Status = "missing") -> MetricValue:
    """利润率 / 回报率类：分子可以为负。"""
    if num is None or den is None:
        return _missing("div", inputs)
    if den <= 0:
        return MetricValue(None, den_nonpositive, inputs, "div")
    return MetricValue(num / den, "ok", inputs, "div")


def _growth(cur: float | None, base: float | None, inputs) -> MetricValue:
    if cur is None or base is None or base <= 0:
        return _missing("growth", inputs)
    return MetricValue(cur / base - 1, "ok", inputs, "growth")


def _num(d: dict | None, key: str) -> float | None:
    if not d:
        return None
    v = d.get(key)
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def compute_metrics(inp: StockInputs) -> dict[str, MetricValue]:
    """估值 / 成长 / 盈利能力 / 动量共 36 项（EPS 修正见 revisions.compute_revisions）。"""
    q, cf, bal = inp.quarters_income, inp.quarters_cash, inp.balance
    fy1, fy2 = inp.fy1, inp.fy2
    enough_analysts = analyst_count(fy1) >= MIN_ANALYSTS
    est_meta = {
        "n_analysts": analyst_count(fy1),
        "eps_fy1": _num(fy1, "epsAvg"), "eps_fy2": _num(fy2, "epsAvg"),
        "fy1_date": fy1.get("date") if fy1 else None, "fy2_date": fy2.get("date") if fy2 else None,
    }

    price = inp.price
    mcap = price * inp.shares_diluted if (price is not None and inp.shares_diluted) else None
    debt, cash_st = _num(bal, "totalDebt"), _num(bal, "cashAndShortTermInvestments")
    equity, assets = _num(bal, "totalStockholdersEquity"), _num(bal, "totalAssets")
    ev = mcap + debt - cash_st if (mcap is not None and debt is not None and cash_st is not None) else None

    rev, rev_p, rev_3 = ttm(q, "revenue"), ttm(q, "revenue", 4), ttm(q, "revenue", 12)
    ebitda, ebitda_p = ttm(q, "ebitda"), ttm(q, "ebitda", 4)
    ebit, ebit_p = ttm(q, "ebit"), ttm(q, "ebit", 4)
    eps, eps_p = ttm(q, "epsDiluted"), ttm(q, "epsDiluted", 4)
    gross, net = ttm(q, "grossProfit"), ttm(q, "netIncome")
    pretax, tax = ttm(q, "incomeBeforeTax"), ttm(q, "incomeTaxExpense")
    ocf = ttm(cf, "operatingCashFlow")
    capex = ttm(cf, "capitalExpenditure")
    fcf = ocf + capex if (ocf is not None and capex is not None) else None

    def fwd(key):  # NTM 一致预期，分析师不足时视为缺失
        return ntm(fy1, fy2, key, inp.as_of) if enough_analysts else None

    eps_ntm, rev_ntm = fwd("epsAvg"), fwd("revenueAvg")
    ebitda_ntm, ebit_ntm = fwd("ebitdaAvg"), fwd("ebitAvg")

    def fy0(key):
        r = fiscal_year_actual(q, key)
        return r[1] if r else None

    out: dict[str, MetricValue] = {}
    nm, na = "not_meaningful", "not_applicable"

    # ---- 估值 ----
    out["pe_ttm"] = _multiple(price, eps, [("price", price), ("eps_ttm", eps)], den_nonpositive=nm)
    out["pe_fwd"] = _multiple(price, eps_ntm, [("price", price), ("eps_ntm", eps_ntm)], den_nonpositive=nm)
    if enough_analysts:
        out["pe_fwd"].meta = est_meta

    eps_growth = (eps / eps_p - 1) if (eps is not None and eps_p is not None and eps_p > 0) else None
    out["peg_ttm"] = _peg(out["pe_ttm"], eps_growth)
    e1, e2 = (_num(fy1, "epsAvg"), _num(fy2, "epsAvg")) if enough_analysts else (None, None)
    fwd_growth = (e2 / e1 - 1) if (e1 is not None and e2 is not None and e1 > 0) else None
    out["peg_fwd"] = _peg(out["pe_fwd"], fwd_growth, nonpositive_base=(e1 is not None and e1 <= 0))

    out["ps_ttm"] = _multiple(mcap, rev, [("market_cap", mcap), ("rev_ttm", rev)], den_nonpositive=nm)
    out["ps_fwd"] = _multiple(mcap, rev_ntm, [("market_cap", mcap), ("rev_ntm", rev_ntm)], den_nonpositive=nm)
    for key, den, lab in [("ev_sales_ttm", rev, "rev_ttm"), ("ev_sales_fwd", rev_ntm, "rev_ntm"),
                          ("ev_ebitda_ttm", ebitda, "ebitda_ttm"), ("ev_ebitda_fwd", ebitda_ntm, "ebitda_ntm"),
                          ("ev_ebit_ttm", ebit, "ebit_ttm"), ("ev_ebit_fwd", ebit_ntm, "ebit_ntm")]:
        out[key] = _multiple(ev, den, [("ev", ev), (lab, den)], den_nonpositive=nm)
    out["pb"] = _multiple(mcap, equity, [("market_cap", mcap), ("equity", equity)], den_nonpositive=na)
    out["pcf"] = _multiple(mcap, ocf, [("market_cap", mcap), ("ocf_ttm", ocf)], den_nonpositive=nm)

    # ---- 成长 ----
    out["rev_yoy"] = _growth(rev, rev_p, [("rev_ttm", rev), ("rev_ttm_prev", rev_p)])
    rev_fy1 = _num(fy1, "revenueAvg") if enough_analysts else None
    out["rev_fwd"] = _growth(rev_fy1, fy0("revenue"), [("rev_fy1", rev_fy1), ("rev_fy0", fy0("revenue"))])

    if rev is not None and rev_3 is not None and rev > 0 and rev_3 > 0:
        out["rev_cagr3"] = MetricValue((rev / rev_3) ** (1 / 3) - 1, "ok", [("rev_ttm", rev), ("rev_ttm_3y", rev_3)],
                                       "cagr3")
    else:
        out["rev_cagr3"] = _missing("cagr3", [("rev_ttm", rev), ("rev_ttm_3y", rev_3)])
    out["ebitda_yoy"] = _growth(ebitda, ebitda_p, [("ebitda_ttm", ebitda), ("ebitda_ttm_prev", ebitda_p)])
    ebitda_fy1 = _num(fy1, "ebitdaAvg") if enough_analysts else None
    out["ebitda_fwd"] = _growth(ebitda_fy1, fy0("ebitda"), [("ebitda_fy1", ebitda_fy1), ("ebitda_fy0", fy0("ebitda"))])
    out["ebit_yoy"] = _growth(ebit, ebit_p, [("ebit_ttm", ebit), ("ebit_ttm_prev", ebit_p)])
    ebit_fy1 = _num(fy1, "ebitAvg") if enough_analysts else None
    out["ebit_fwd"] = _growth(ebit_fy1, fy0("ebit"), [("ebit_fy1", ebit_fy1), ("ebit_fy0", fy0("ebit"))])
    out["eps_yoy"] = _growth(eps, eps_p, [("eps_ttm", eps), ("eps_ttm_prev", eps_p)])
    eps_fy1 = _num(fy1, "epsAvg") if enough_analysts else None
    out["eps_fwd"] = _growth(eps_fy1, fy0("epsDiluted"), [("eps_fy1", eps_fy1), ("eps_fy0", fy0("epsDiluted"))])

    # ---- 盈利能力 ----
    out["gross_m"] = _ratio(gross, rev, [("gross_ttm", gross), ("rev_ttm", rev)])
    out["ebit_m"] = _ratio(ebit, rev, [("ebit_ttm", ebit), ("rev_ttm", rev)])
    out["ebitda_m"] = _ratio(ebitda, rev, [("ebitda_ttm", ebitda), ("rev_ttm", rev)])
    out["net_m"] = _ratio(net, rev, [("net_ttm", net), ("rev_ttm", rev)])
    out["fcf_m"] = _ratio(fcf, rev, [("fcf_ttm", fcf), ("rev_ttm", rev)])
    out["roe"] = _ratio(net, equity, [("net_ttm", net), ("equity", equity)], den_nonpositive=na)
    out["roa"] = _ratio(net, assets, [("net_ttm", net), ("assets", assets)])
    tax_rate = min(max(tax / pretax, 0.0), 0.5) if (tax is not None and pretax and pretax > 0) else 0.21
    nopat = ebit * (1 - tax_rate) if ebit is not None else None
    invested = (debt + equity - cash_st) if (debt is not None and equity is not None and cash_st is not None) else None
    out["roic"] = _ratio(nopat, invested, [("nopat", nopat), ("invested", invested)], den_nonpositive=na)
    out["asset_turn"] = _ratio(rev, assets, [("rev_ttm", rev), ("assets", assets)])

    if inp.sector_key == "financials":
        # 金融股：报表营收是总收入口径（含利息收入）而分析师预期是净收入口径，二者不可比；
        # 经营现金流含存贷款变动，现金流类指标没有意义
        out["rev_fwd"] = MetricValue(None, "not_applicable", out["rev_fwd"].inputs, "growth",
                                     {"reason": "financials_revenue_basis"})
        for key in ("pcf", "fcf_m"):
            out[key] = MetricValue(None, "not_applicable", out[key].inputs, out[key].op,
                                   {"reason": "financials_cash_flow"})

    # ---- 动量 ----
    closes = inp.closes
    for key, n in MOMENTUM_WINDOWS.items():
        if len(closes) > n and closes[-1 - n] > 0:
            out[key] = MetricValue(closes[-1] / closes[-1 - n] - 1, "ok",
                                   [("close_now", closes[-1]), ("close_then", closes[-1 - n])], "ret", {"days": n})
        else:
            out[key] = _missing("ret")
    return out


def _peg(pe: MetricValue, growth: float | None, *, nonpositive_base: bool = False) -> MetricValue:
    """PEG = 市盈率 / (EPS 增速 × 100)。市盈率本身无意义或增速 ≤ 0 → 无意义。"""
    inputs = [("pe", pe.value), ("growth_pct", growth * 100 if growth is not None else None)]
    if pe.status == "not_meaningful" or nonpositive_base:
        return MetricValue(None, "not_meaningful", inputs, "peg")
    if pe.status != "ok" or growth is None:
        return _missing("peg", inputs)
    if growth <= 0:
        return MetricValue(None, "not_meaningful", inputs, "peg")
    return MetricValue(pe.value / (growth * 100), "ok", inputs, "peg")  # type: ignore[operator]
