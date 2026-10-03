"""港股：样本元数据（港股通标记、行业、财年、股本、市值、最新报告期）+ 逐只拉三大报表并归一化为累计报告。

注意：东财港股报表金额**一律是人民币**（美元 / 港元 / 欧元申报的公司已按期末汇率折算，人民币申报的保持原值；
报告清单的 CURRENCY 是原始申报币种）。换算成港元在 pipeline 里做（股价是港元）。
科目名按公司类型不同（一般企业 / 银行 / 保险 / 证券），按候选顺序取第一个有值的科目。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from app.services.quant_research.cnhk import eastmoney as em
from app.services.quant_research.cnhk.sectors import hk_sector

_F10 = {"source": "F10", "client": "PC"}
_ITEM_COLS = "SECUCODE,SECURITY_CODE,REPORT_DATE,STD_ITEM_NAME,AMOUNT"
HISTORY_YEARS = 4.6          # 16 季 + 上一财年的累计基点
FINANCIAL_ORG_TYPES = {"银行", "保险", "证券"}

_REVENUE = ("营业额", "营运收入", "经营收入总额", "经营收入")
_EQUITY = ("股东权益", "归属于母公司股东权益")
_CASH = ("现金及等价物", "短期存款")
_DEBT = ("短期贷款", "长期贷款", "银行贷款及透支", "长期银行贷款", "借款", "应付票据(非流动)",
         "融资租赁负债(流动)", "融资租赁负债(非流动)")
_CAPEX = ("购建固定资产", "购建无形资产及其他资产")


def _first(items: dict[str, float], names: tuple[str, ...]) -> float | None:
    return next((items[n] for n in names if items.get(n) is not None), None)


def _sum(items: dict[str, float], names: tuple[str, ...]) -> float | None:
    vals = [items[n] for n in names if items.get(n) is not None]
    return sum(vals) if vals else None


def _group(rows: list[dict]) -> dict[str, dict[str, float]]:
    """长表 → {报告期: {科目: 金额}}。"""
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("AMOUNT") is None or not r.get("REPORT_DATE"):
            continue
        try:
            out.setdefault(str(r["REPORT_DATE"])[:10], {})[str(r["STD_ITEM_NAME"])] = float(r["AMOUNT"])
        except (TypeError, ValueError):
            continue
    return out


# ---------- 归一化（纯函数） ----------

def hk_reports(income_rows: list[dict], cash_rows: list[dict], report_list: list[dict], fy_end: str,
               financial: bool) -> list[dict]:
    """三张长表 + 报告清单 → 累计报告（新 → 旧）。金额为人民币（见模块说明）。"""
    inc_by, cash_by = _group(income_rows), _group(cash_rows)
    meta = {str(x.get("REPORT_DATE"))[:10]: x for x in report_list}
    out = []
    for d, inc in inc_by.items():
        cf = cash_by.get(d, {})
        pretax = inc.get("除税前溢利")
        ebit = da = gross = None
        if not financial:
            gross = inc.get("毛利")
            finance_cost = inc.get("融资成本")
            ebit = pretax + abs(finance_cost or 0.0) if pretax is not None else None  # EBIT = 除税前溢利 + 融资成本
            da = cf.get("加:折旧及摊销") if cf.get("加:折旧及摊销") is not None else inc.get("折旧和摊销")
        capex = _sum(cf, _CAPEX)
        eps = inc.get("每股摊薄盈利")
        m = meta.get(d, {})
        out.append({
            "report_date": d, "notice_date": None, "fy_end": fy_end, "currency": m.get("CURRENCY"),
            "revenue": _first(inc, _REVENUE), "gross": gross, "ebit": ebit, "net": inc.get("股东应占溢利"),
            "eps": eps if eps is not None else inc.get("每股基本盈利"), "pretax": pretax, "tax": inc.get("税项"),
            "da": da, "ocf": cf.get("经营业务现金净额"), "cfi": cf.get("投资业务现金净额"),
            "cff": cf.get("融资业务现金净额"), "capex": -abs(capex) if capex is not None else None,
        })
    return sorted(out, key=lambda r: r["report_date"], reverse=True)


def hk_balance(balance_rows: list[dict], financial: bool) -> dict | None:
    """最新一期资产负债表 → FMP 同名字段（人民币）。金融类不给借款 / 现金。"""
    by = _group(balance_rows)
    if not by:
        return None
    d = max(by)
    items = by[d]
    out = {"date": d, "totalAssets": items.get("总资产"), "totalStockholdersEquity": _first(items, _EQUITY),
           "totalDebt": None, "cashAndShortTermInvestments": None}
    if not financial:
        out["totalDebt"] = _sum(items, _DEBT) or 0.0
        out["cashAndShortTermInvestments"] = _sum(items, _CASH)
    return out


# ---------- 取数 ----------

@dataclass(frozen=True)
class HkMeta:
    code: str
    name: str
    industry: str | None
    sector: str | None
    fy_end: str
    org_type: str | None
    shares: float | None
    market_cap: float | None      # 港元
    latest_report: str | None
    connect: bool                 # 港股通标的

    @property
    def financial(self) -> bool:
        return self.org_type in FINANCIAL_ORG_TYPES


async def fetch_meta(client: httpx.AsyncClient, today: date, codes: list[str] | None = None) -> dict[str, HkMeta]:
    """港股元数据；codes 给定时只取这些代码（样本外现算）。"""
    flt = f'(SECURITY_CODE in ({",".join(chr(34) + c + chr(34) for c in codes)}))' if codes else None
    since = (today - timedelta(days=430)).isoformat()
    ind_flt = f"(REPORT_DATE>='{since}')" + (flt or "")
    info, prof, ind = await asyncio.gather(
        em.table(client, "RPT_HKF10_INFO_SECURITYINFO",
                 "SECURITY_CODE,SECURITY_NAME_ABBR,GANGGUTONGBIAODISHEN,GANGGUTONGBIAODIHU", flt),
        em.table(client, "RPT_HKF10_INFO_ORGPROFILE", "SECURITY_CODE,SECURITY_NAME_ABBR,BELONG_INDUSTRY,YEAR_SETTLE_DAY",
                 flt),
        em.table(client, "RPT_HKF10_FN_MAININDICATOR",
                 "SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,ISSUED_COMMON_SHARES,TOTAL_MARKET_CAP,ORG_TYPE,FISCAL_YEAR",
                 ind_flt, max_pages=60),
    )
    connect = {r["SECURITY_CODE"] for r in info if "是" in (r.get("GANGGUTONGBIAODISHEN"), r.get("GANGGUTONGBIAODIHU"))}
    names = {r["SECURITY_CODE"]: r.get("SECURITY_NAME_ABBR") for r in info}
    profile = {r["SECURITY_CODE"]: r for r in prof}
    latest: dict[str, dict] = {}
    for r in ind:
        c = r.get("SECURITY_CODE")
        if c and (c not in latest or str(r["REPORT_DATE"]) > str(latest[c]["REPORT_DATE"])):
            latest[c] = r
    out: dict[str, HkMeta] = {}
    for c, r in latest.items():
        p = profile.get(c, {})
        industry = p.get("BELONG_INDUSTRY")
        fy_end = str(p.get("YEAR_SETTLE_DAY") or r.get("FISCAL_YEAR") or "12-31")
        out[c] = HkMeta(c, str(names.get(c) or p.get("SECURITY_NAME_ABBR") or r.get("SECURITY_NAME_ABBR") or c),
                        industry, hk_sector(c, industry), fy_end, r.get("ORG_TYPE"),
                        _f(r.get("ISSUED_COMMON_SHARES")), _f(r.get("TOTAL_MARKET_CAP")),
                        str(r["REPORT_DATE"])[:10], c in connect)
    return out


def _f(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


MIN_MARKET_CAP_HKD = 2e9


def pick_universe(meta: dict[str, HkMeta]) -> list[str]:
    """港股通标的 ∪ 总市值 ≥ 20 亿港元；去掉人民币柜台（8 开头的 5 位代码）、行业未映射、无股本。"""
    out = [m.code for m in meta.values()
           if (m.connect or (m.market_cap or 0) >= MIN_MARKET_CAP_HKD) and m.sector and m.shares
           and not m.code.startswith("8")]
    return sorted(out)


async def fetch_reports(client: httpx.AsyncClient, m: HkMeta, today: date) -> tuple[list[dict], dict | None]:
    """一只港股近 4.6 年的累计报告与最新资产负债表（人民币）。"""
    secu = em.secucode_hk(m.code)
    listing = await em.table(client, "RPT_CUSTOM_HKSK_APPFN_CASHFLOW_SUMMARY",
                             "SECUCODE,SECURITY_CODE,REPORT_DATE,CURRENCY,REPORT_TYPE",
                             f'(SECUCODE="{secu}")', extra={**_F10, "quoteColumns": ""}, max_pages=1)
    report_list = (listing[0].get("REPORT_LIST") or []) if listing else []
    cutoff = (today - timedelta(days=int(HISTORY_YEARS * 365))).isoformat()
    dates = [str(x["REPORT_DATE"])[:10] for x in report_list if str(x.get("REPORT_DATE"))[:10] >= cutoff]
    if not dates:
        return [], None
    flt = f'(SECUCODE="{secu}")(REPORT_DATE in ({",".join(repr(d) for d in dates)}))'
    inc, cash, bal = await asyncio.gather(
        em.table(client, "RPT_HKF10_FN_INCOME_PC", _ITEM_COLS, flt, extra=_F10),
        em.table(client, "RPT_HKF10_FN_CASHFLOW_PC", _ITEM_COLS, flt, extra=_F10),
        em.table(client, "RPT_HKF10_FN_BALANCE_PC", _ITEM_COLS, f'(SECUCODE="{secu}")(REPORT_DATE=\'{max(dates)}\')',
                 extra=_F10),
    )
    return hk_reports(inc, cash, report_list, m.fy_end, m.financial), hk_balance(bal, m.financial)
