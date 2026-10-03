"""A 股：报表按报告期批量拉取（全市场）、股本 / 市值 / 行业、个股按代码补拉。归一化为 reports.py 的累计报告格式。

报表分四类公司（G 一般企业 / B 银行 / S 券商 / I 保险），字段大多同名；金融类没有营业成本、利息费用、折旧摊销，
不算毛利 / EBIT / EBITDA，资产负债表也不取借款与现金（企业价值对金融股无意义）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from app.core.logging import logger
from app.services.quant_research.cnhk import eastmoney as em
from app.services.quant_research.cnhk.sectors import cn_sector

_KEY = "SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,NOTICE_DATE"
# 利润表：一般企业表（G）其实含全部公司，ORG_TYPE 标出 通用 / 银行 / 证券 / 保险；金融类的营业成本、利息费用为空
INCOME_COLUMNS = (_KEY + ",ORG_TYPE,TOTAL_OPERATE_INCOME,OPERATE_INCOME,OPERATE_COST,TOTAL_PROFIT,INCOME_TAX,"
                  "PARENT_NETPROFIT,BASIC_EPS,DILUTED_EPS,FE_INTEREST_EXPENSE,FINANCE_EXPENSE")
_FIN_CASH = _KEY + ",NETCASH_OPERATE,NETCASH_INVEST,NETCASH_FINANCE,CONSTRUCT_LONG_ASSET"
_FIN_BALANCE = _KEY + ",TOTAL_ASSETS,TOTAL_LIABILITIES,TOTAL_PARENT_EQUITY,TOTAL_EQUITY"
# 现金流量表 / 资产负债表按公司类型分表
COLUMNS: dict[str, tuple[str, str]] = {
    "G": (
        _FIN_CASH + ",FA_IR_DEPR,OILGAS_BIOLOGY_DEPR,IR_DEPR,IA_AMORTIZE,LPE_AMORTIZE,USERIGHT_ASSET_AMORTIZE",
        _FIN_BALANCE + ",MONETARYFUNDS,TRADE_FINASSET,TRADE_FINASSET_NOTFVTPL,SHORT_LOAN,LONG_LOAN,BOND_PAYABLE,"
                       "NONCURRENT_LIAB_1YEAR,SHORT_BOND_PAYABLE,LEASE_LIAB",
    ),
    "B": (_FIN_CASH, _FIN_BALANCE),
    "S": (_FIN_CASH, _FIN_BALANCE),
    "I": (_FIN_CASH, _FIN_BALANCE),
}
ORG_KIND = {"通用": "G", "银行": "B", "证券": "S", "保险": "I"}
FIRST_PERIOD = date(2022, 6, 30)        # 最新一季往回 16 季 + 1 个累计基点
OPEN_WINDOW_DAYS = 125                   # 年报最晚次年 4 月底披露：报告期后 125 天内都可能有新数据
_DA_COLS = ("FA_IR_DEPR", "OILGAS_BIOLOGY_DEPR", "IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE")
_DEBT_COLS = ("SHORT_LOAN", "LONG_LOAN", "BOND_PAYABLE", "NONCURRENT_LIAB_1YEAR", "SHORT_BOND_PAYABLE", "LEASE_LIAB")


def _f(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _sum(row: dict, cols: tuple[str, ...]) -> float | None:
    vals = [_f(row.get(c)) for c in cols]
    known = [v for v in vals if v is not None]
    return sum(known) if known else None


# ---------- 归一化（纯函数） ----------

def cn_report(kind: str, income: dict, cash: dict | None) -> dict:
    """一行利润表 + 同期现金流量表 → 累计报告。"""
    cash = cash or {}
    general = kind == "G"
    pretax, tax = _f(income.get("TOTAL_PROFIT")), _f(income.get("INCOME_TAX"))
    revenue = _f(income.get("TOTAL_OPERATE_INCOME")) if general else None
    revenue = revenue if revenue is not None else _f(income.get("OPERATE_INCOME"))
    gross = ebit = da = None
    if general:
        op_income = _f(income.get("OPERATE_INCOME"))
        cost = _f(income.get("OPERATE_COST"))
        base = op_income if op_income is not None else revenue
        gross = base - cost if (base is not None and cost is not None) else None
        interest = _f(income.get("FE_INTEREST_EXPENSE"))
        interest = interest if interest is not None else _f(income.get("FINANCE_EXPENSE"))
        ebit = pretax + (interest or 0.0) if pretax is not None else None  # EBIT = 利润总额 + 利息费用
        da = _sum(cash, _DA_COLS)
    capex = _f(cash.get("CONSTRUCT_LONG_ASSET"))
    eps = _f(income.get("DILUTED_EPS"))
    return {
        "report_date": str(income["REPORT_DATE"])[:10], "notice_date": str(income.get("NOTICE_DATE") or "")[:10] or None,
        "fy_end": "12-31", "revenue": revenue, "gross": gross, "ebit": ebit, "net": _f(income.get("PARENT_NETPROFIT")),
        "eps": eps if eps is not None else _f(income.get("BASIC_EPS")), "pretax": pretax, "tax": tax, "da": da,
        "ocf": _f(cash.get("NETCASH_OPERATE")), "cfi": _f(cash.get("NETCASH_INVEST")),
        "cff": _f(cash.get("NETCASH_FINANCE")), "capex": -capex if capex is not None else None,
    }


def cn_balance(kind: str, row: dict) -> dict:
    """资产负债表 → FMP 同名字段。一般企业借款项全空视为无有息负债（0）；金融类不给借款 / 现金。"""
    equity = _f(row.get("TOTAL_PARENT_EQUITY"))
    out = {"date": str(row["REPORT_DATE"])[:10], "totalAssets": _f(row.get("TOTAL_ASSETS")),
           "totalStockholdersEquity": equity if equity is not None else _f(row.get("TOTAL_EQUITY")),
           "totalDebt": None, "cashAndShortTermInvestments": None}
    if kind == "G":
        cash = _f(row.get("MONETARYFUNDS"))
        trade = _f(row.get("TRADE_FINASSET_NOTFVTPL"))
        trade = trade if trade is not None else _f(row.get("TRADE_FINASSET"))
        out["cashAndShortTermInvestments"] = (cash or 0.0) + (trade or 0.0) if cash is not None else None
        out["totalDebt"] = _sum(row, _DEBT_COLS) or 0.0
    return out


def quarter_ends(start: date, end: date) -> list[date]:
    """区间 [start, end] 内的季末日（升序）。"""
    out, y, m = [], start.year, ((start.month - 1) // 3 + 1) * 3
    while True:
        d = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        if d > end:
            return out
        if d >= start:
            out.append(d)
        m += 3
        if m > 12:
            m, y = m - 12, y + 1


def open_periods(today: date) -> list[date]:
    """仍可能有新披露的报告期（报告期后 OPEN_WINDOW_DAYS 天内）。"""
    return [d for d in quarter_ends(today - timedelta(days=OPEN_WINDOW_DAYS + 92), today)
            if (today - d).days <= OPEN_WINDOW_DAYS]


def assemble(income: list[dict], cash: list[dict], balance: list[dict]) -> dict[str, dict]:
    """三表行 → {代码: {"name", "kind", "reports": [...], "balances": [...]}}。

    公司类型取利润表的 ORG_TYPE；同一代码同一报告期有多行时取披露日最新的一行。
    """
    cash_by = _latest_by(cash)
    out: dict[str, dict] = {}
    for key, inc in _latest_by(income).items():
        kind = ORG_KIND.get(str(inc.get("ORG_TYPE") or ""), "G")
        entry = out.setdefault(key[0], {"name": inc.get("SECURITY_NAME_ABBR"), "kind": kind, "reports": [],
                                        "balances": []})
        entry["reports"].append(cn_report(kind, inc, cash_by.get(key)))
    for key, bal in _latest_by(balance).items():
        entry = out.get(key[0])
        if entry is not None:
            entry["balances"].append(cn_balance(entry["kind"], bal))
    for entry in out.values():
        entry["reports"].sort(key=lambda r: r["report_date"], reverse=True)
        entry["balances"].sort(key=lambda b: b["date"], reverse=True)
    return out


def _latest_by(rows: list[dict]) -> dict[tuple[str, str], dict]:
    best: dict[tuple[str, str], dict] = {}
    for r in rows:
        if not r.get("SECURITY_CODE") or not r.get("REPORT_DATE"):
            continue
        key = (str(r["SECURITY_CODE"]), str(r["REPORT_DATE"])[:10])
        if key not in best or str(r.get("NOTICE_DATE") or "") > str(best[key].get("NOTICE_DATE") or ""):
            best[key] = r
    return best


# ---------- 取数 ----------

async def fetch_periods(client: httpx.AsyncClient, periods: list[date], balance_periods: list[date],
                        keep: set[str] | None = None) -> dict[str, dict]:
    """全市场按报告期拉三表（现金流 / 资产负债表四类公司各一张），返回 assemble 结果。

    keep：只保留这些代码的行（样本股票）。全市场约 6500 家 × 18 期，不过滤会在内存里堆十几万行。
    """
    jobs: list[tuple[str, str, str, str]] = []  # (表名, 列, 过滤, 归类)
    for d in periods:
        flt = f"(REPORT_DATE='{d.isoformat()}'){em.A_SHARE_TYPES}"
        jobs.append(("RPT_F10_FINANCE_GINCOME", INCOME_COLUMNS, flt, "income"))
        for kind, (cash_cols, bal_cols) in COLUMNS.items():
            jobs.append((f"RPT_F10_FINANCE_{kind}CASHFLOW", cash_cols, flt, "cash"))
            if d in balance_periods:
                jobs.append((f"RPT_F10_FINANCE_{kind}BALANCE", bal_cols, flt, "balance"))
    rows: dict[str, list[dict]] = {"income": [], "cash": [], "balance": []}

    async def run(name: str, cols: str, flt: str, bucket: str) -> None:
        res = await em.table(client, name, cols, flt)
        rows[bucket].extend(r for r in res if keep is None or str(r.get("SECURITY_CODE")) in keep)

    await asyncio.gather(*(run(*job) for job in jobs))
    logger.info("quant_cn_periods_fetched", periods=len(periods), income_rows=len(rows["income"]))
    return assemble(rows["income"], rows["cash"], rows["balance"])


async def fetch_symbol(client: httpx.AsyncClient, code: str, since: date = FIRST_PERIOD) -> dict | None:
    """单只股票的全部报告期（样本外现算用）：先取利润表定公司类型，再取对应的现金流 / 资产负债表。"""
    flt = f'(SECURITY_CODE="{code}")(REPORT_DATE>=\'{since.isoformat()}\')'
    income = await em.table(client, "RPT_F10_FINANCE_GINCOME", INCOME_COLUMNS, flt)
    if not income:
        return None
    kind = ORG_KIND.get(str(income[0].get("ORG_TYPE") or ""), "G")
    cash_cols, bal_cols = COLUMNS[kind]
    cash, bal = await asyncio.gather(em.table(client, f"RPT_F10_FINANCE_{kind}CASHFLOW", cash_cols, flt),
                                     em.table(client, f"RPT_F10_FINANCE_{kind}BALANCE", bal_cols, flt))
    return assemble(income, cash, bal).get(code)


@dataclass(frozen=True)
class CnMeta:
    code: str
    name: str
    industry: str | None
    sector: str | None
    shares: float | None
    market_cap: float | None
    trade_date: str


async def fetch_market_meta(client: httpx.AsyncClient) -> dict[str, CnMeta]:
    """全部 A 股的最新总股本、总市值、行业（按最近一个有数据的交易日）。"""
    latest = await em.table(client, "RPT_VALUEANALYSIS_DET", "TRADE_DATE", None, base=em.WEB,
                            sort=("TRADE_DATE", "-1"), max_pages=1, extra={"pageSize": "1"})
    if not latest:
        return {}
    day = str(latest[0]["TRADE_DATE"])[:10]
    rows = await em.table(client, "RPT_VALUEANALYSIS_DET",
                          "SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,TOTAL_MARKET_CAP,TOTAL_SHARES",
                          f"(TRADE_DATE='{day}')", base=em.WEB)
    out = {}
    for r in rows:
        code = str(r.get("SECURITY_CODE") or "")
        if len(code) != 6:
            continue
        out[code] = CnMeta(code, str(r.get("SECURITY_NAME_ABBR") or code), r.get("BOARD_NAME"),
                           cn_sector(r.get("BOARD_NAME")), _f(r.get("TOTAL_SHARES")), _f(r.get("TOTAL_MARKET_CAP")), day)
    return out


UNIVERSE_SIZE = 1800


def pick_universe(meta: dict[str, CnMeta], size: int = UNIVERSE_SIZE) -> list[str]:
    """总市值前 size 只（剔除 ST / 退市整理、行业未映射、无股本）。"""
    ok = [m for m in meta.values() if m.sector and m.shares and m.market_cap
          and "ST" not in m.name.upper() and "退" not in m.name]
    ok.sort(key=lambda m: m.market_cap or 0, reverse=True)
    return [m.code for m in ok[:size]]
