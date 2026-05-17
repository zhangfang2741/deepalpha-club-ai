"""FMP 多类型数据拉取：K线、财务、指标、股息、拆分等。"""
from __future__ import annotations

import os

import httpx

_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_FMP_BASE = "https://financialmodelingprep.com/stable"

# FMP 收费版才有足够历史，免费 key 只能看少量数据
# key 配置在 .env 或 Railway 环境变量
if not _FMP_KEY:
    import warnings
    warnings.warn("FMP_API_KEY not set, data endpoints will return demo data")


async def _get(url: str, params: dict | None = None) -> list[dict]:
    """通用 GET，失败返回空列表（部分数据 API Key 可能受限）"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params={**(params or {}), "apikey": _FMP_KEY})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "Error Message" in data:
                return []
            return data if isinstance(data, list) else []
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 基础价格（已存在，下游复用）
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_fmp_price_eod(symbol: str, from_: str, to: str, period: str = "daily") -> list[dict]:
    """日/周线 EOD 价格。返回 list[dict]，每条包含 date/open/high/low/close/volume。"""
    url = f"{_FMP_BASE}/historical-price-eod/full"
    rows = await _get(url, {"symbol": symbol, "from": from_, "to": to, "period": period})
    return [
        {"date": r["date"], "open": r["open"], "high": r["high"],
         "low": r["low"], "close": r["close"], "volume": r.get("volume", 0)}
        for r in sorted(rows, key=lambda x: x["date"])
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 财务三大表（季度）
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_income_statement(symbol: str, limit: int = 40) -> list[dict]:
    """利润表（季度），返回 list[dict] 含 date/netIncome/revenue/eps 等。"""
    url = f"{_FMP_BASE}/income-statement"
    rows = await _get(url, {"symbol": symbol, "period": "quarter", "limit": limit})
    return [
        {"date": r["date"], "revenue": r.get("revenue"), "netIncome": r.get("netIncome"),
         "grossProfit": r.get("grossProfit"), "operatingIncome": r.get("operatingIncome"),
         "eps": r.get("eps"), "epsDiluted": r.get("epsDiluted")}
        for r in rows
    ]


async def fetch_balance_sheet(symbol: str, limit: int = 40) -> list[dict]:
    """资产负债表（季度），返回 list[dict] 含 date/totalAssets/totalLiabilities/equity 等。"""
    url = f"{_FMP_BASE}/balance-sheet-statement"
    rows = await _get(url, {"symbol": symbol, "period": "quarter", "limit": limit})
    return [
        {"date": r["date"], "totalAssets": r.get("totalAssets"), "totalLiabilities": r.get("totalLiabilities"),
         "totalEquity": r.get("totalEquity"), "cash": r.get("cashAndShortTermInvestments"),
         "debt": r.get("totalDebt")}
        for r in rows
    ]


async def fetch_cash_flow(symbol: str, limit: int = 40) -> list[dict]:
    """现金流量表（季度），返回 list[dict] 含 date/operatingCashFlow/freeCashFlow 等。"""
    url = f"{_FMP_BASE}/cash-flow-statement"
    rows = await _get(url, {"symbol": symbol, "period": "quarter", "limit": limit})
    return [
        {"date": r["date"], "operatingCashFlow": r.get("operatingCashFlow"),
         "freeCashFlow": r.get("freeCashFlow"), "capex": r.get("capex"),
         "dividendsPaid": r.get("dividendsPaid")}
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 关键指标 & 比率
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_key_metrics(symbol: str, limit: int = 40) -> list[dict]:
    """关键指标（季度），返回 PE/PEgr/ROE/ROA/ROS/GPM 等。"""
    url = f"{_FMP_BASE}/key-metrics"
    rows = await _get(url, {"symbol": symbol, "period": "quarter", "limit": limit})
    return [
        {"date": r["date"], "pe": r.get("peRatio"), "pb": r.get("priceToBookRatio"),
         "ps": r.get("priceToSalesRatio"), "roe": r.get("roe"), "roa": r.get("roa"),
         "ros": r.get("returnOnNetOperatingAssets"), "gpm": r.get("grossProfitMargin"),
         "npm": r.get("netProfitMargin"), "de": r.get("debtToEquityRatio"),
         "currentRatio": r.get("currentRatio"), "quickRatio": r.get("quickRatio"),
         "dividendYield": r.get("dividendYield")}
        for r in rows
    ]


async def fetch_financial_ratios(symbol: str, limit: int = 40) -> list[dict]:
    """财务比率（季度），返回更多推导比率。"""
    url = f"{_FMP_BASE}/financial-ratios"
    rows = await _get(url, {"symbol": symbol, "period": "quarter", "limit": limit})
    return [
        {"date": r["date"], "pe": r.get("perShareRatio", {}).get("peRatio"),
         "pb": r.get("perShareRatio", {}).get("pbRatio"),
         "ps": r.get("perShareRatio", {}).get("psRatio"),
         "dividendPerShare": r.get("perShareRatio", {}).get("dividendPerShare"),
         "payoutRatio": r.get("dividendSheet", {}).get("payoutRatio")}
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 估值
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_dcf_history(symbol: str) -> list[dict]:
    """DCF 估值历史，返回 list[dict] 含 date/dcf/sharePrice。"""
    url = f"{_FMP_BASE}/dcf"
    rows = await _get(url, {"symbol": symbol})
    return [
        {"date": r["date"], "dcf": r.get("dcf"), "sharePrice": r.get("sharePrice")}
        for r in rows
    ]


async def fetch_historical_market_cap(symbol: str) -> list[dict]:
    """历史市值/股权价值。"""
    url = f"{_FMP_BASE}/historical-market-cap"
    rows = await _get(url, {"symbol": symbol})
    return [
        {"date": r["date"], "marketCap": r.get("marketCap"), "stockPrice": r.get("stockPrice")}
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 股票特殊数据
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_dividends(symbol: str, limit: int = 40) -> list[dict]:
    """股息历史（年度），返回 date/dividendAmount/yield。"""
    url = f"{_FMP_BASE}/historical-price-dividend"
    rows = await _get(url, {"symbol": symbol})
    return [
        {"date": r.get("date"), "dividendAmount": r.get("dividend"), "yield": r.get("dividendYield")}
        for r in rows[-limit:]
    ]


async def fetch_splits(symbol: str) -> list[dict]:
    """股票拆分历史。"""
    url = f"{_FMP_BASE}/stock-split"
    rows = await _get(url, {"symbol": symbol})
    return [{"date": r.get("date"), "splitRatio": r.get("splitRatio"), "before": r.get("before"), "after": r.get("after")} for r in rows]


async def fetch_earnings(symbol: str, limit: int = 20) -> list[dict]:
    """盈利预告/财报日程，返回 date/epsActual/epsSurprise/revenueActual。"""
    url = f"{_FMP_BASE}/earnings-calendar"
    rows = await _get(url, {"symbol": symbol, "limit": limit})
    return [
        {"date": r.get("date"), "epsActual": r.get("epsActual"), "epsSurprise": r.get("epsSurprise"),
         "revenueActual": r.get("revenueActual"), "revenueEstimate": r.get("revenueEstimate")}
        for r in rows
    ]


async def fetch_historical_employee_count(symbol: str, limit: int = 20) -> list[dict]:
    """员工历史人数（年度），返回 date/employeeCount。"""
    url = f"{_FMP_BASE}/historical-employee-count"
    rows = await _get(url, {"symbol": symbol, "limit": limit})
    return [
        {"date": r.get("periodOfReport"), "employeeCount": r.get("employeeCount")}
        for r in rows
        if r.get("employeeCount")
    ]


async def fetch_news(symbol: str, limit: int = 50) -> list[dict]:
    """股票新闻列表，返回 date/title/text/sentiment/score。"""
    url = f"{_FMP_BASE}/stock_news"
    rows = await _get(url, {"symbol": symbol, "limit": limit})
    return [
        {"date": r.get("publishedDate"), "title": r.get("title"), "text": r.get("text"),
         "sentiment": r.get("sentiment"), "sentimentScore": r.get("sentimentScore"),
         "source": r.get("source")}
        for r in rows
    ]


async def fetch_analyst_estimates(symbol: str, limit: int = 20) -> list[dict]:
    """分析师共识预测（EPS/Revenue 未来 N 个季度）。"""
    url = f"{_FMP_BASE}/analyst-estimates"
    rows = await _get(url, {"symbol": symbol, "limit": limit})
    return [
        {"date": r.get("date"), "epsAvg": r.get("epsAvg"), "epsHigh": r.get("epsHigh"),
         "epsLow": r.get("epsLow"), "revenueAvg": r.get("revenueAvg"),
         "revenueHigh": r.get("revenueHigh"), "revenueLow": r.get("revenueLow"),
         "numberAnalysts": r.get("numberAnalysts")}
        for r in rows
    ]


async def fetch_company_outlook(symbol: str) -> dict | None:
    """公司完整展望（含评级、目标价、DCF 等）。"""
    url = f"{_FMP_BASE}/company-outlook"
    rows = await _get(url, {"symbol": symbol})
    if not rows:
        return None
    o = rows[0]
    return {
        "symbol": o.get("symbol"), "dcf": o.get("dcf"),
        "stockPrice": o.get("stockPrice"),
        "targetPrice": o.get("priceTarget"),
        "rating": o.get("rating"),
        "beta": o.get("beta"),
        "volAvg": o.get("volAvg"),
    }


async def fetch_profile(symbol: str) -> dict | None:
    """公司概况：行业/市值/员工数/描述等。"""
    url = f"{_FMP_BASE}/profile"
    rows = await _get(url, {"symbol": symbol})
    if not rows:
        return None
    p = rows[0]
    return {
        "symbol": p.get("symbol"), "name": p.get("companyName"),
        "industry": p.get("industry"), "sector": p.get("sector"),
        "marketCap": p.get("mktCap"), "price": p.get("price"),
        "employees": p.get("fullTimeEmployees"), "exchange": p.get("exchange"),
        "description": p.get("description"),
    }


async def fetch_quote(symbol: str) -> dict | None:
    """实时行情。"""
    url = f"{_FMP_BASE}/quote-short"
    rows = await _get(url, {"symbol": symbol})
    if not rows:
        return None
    q = rows[0]
    return {
        "symbol": q.get("symbol"), "price": q.get("price"),
        "change": q.get("change"), "changePercent": q.get("changesPercentage"),
        "high": q.get("dayHigh"), "low": q.get("dayLow"),
        "volume": q.get("volume"), "avgVolume": q.get("avgVolume"),
        "open": q.get("open"), "previousClose": q.get("previousClose"),
        "yearHigh": q.get("yearHigh"), "yearLow": q.get("yearLow"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 宏观经济（用于股票对冲/大盘分析）
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_treasury_yields() -> list[dict]:
    """美国国债收益率曲线（10Y/2Y/1M 等）。"""
    url = f"{_FMP_BASE}/treasury"
    rows = await _get(url)
    return [{"date": r.get("date"), "yield10y": r.get("yield10y"), "yield2y": r.get("yield2y"),
             "yield1m": r.get("yield1m"), "yield30y": r.get("yield30y")} for r in rows]


async def fetch_sp500() -> list[dict]:
    """S&P500 历史行情。"""
    url = f"{_FMP_BASE}/historical-price-eod/sp500"
    rows = await _get(url, {"period": "daily"})
    return [{"date": r["date"], "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "volume": r.get("volume", 0)} for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_all_financial_data(symbol: str) -> dict:
    """一次性拉取 symbol 的所有财务数据（供因子计算用）。"""
    import asyncio
    results = await asyncio.gather(
        fetch_income_statement(symbol),
        fetch_balance_sheet(symbol),
        fetch_cash_flow(symbol),
        fetch_key_metrics(symbol),
        fetch_analyst_estimates(symbol),
        fetch_profile(symbol),
        fetch_earnings(symbol),
        fetch_dividends(symbol),
        fetch_dcf_history(symbol),
        fetch_historical_employee_count(symbol),
        return_exceptions=True,
    )
    return {
        "income_statement": _safe(results, 0),
        "balance_sheet": _safe(results, 1),
        "cash_flow": _safe(results, 2),
        "key_metrics": _safe(results, 3),
        "analyst_estimates": _safe(results, 4),
        "profile": _safe(results, 5) if not isinstance(results[5], Exception) else None,
        "earnings": _safe(results, 6),
        "dividends": _safe(results, 7),
        "dcf": _safe(results, 8),
        "employee_count": _safe(results, 9),
    }


def _safe(results: list, idx: int) -> list[dict] | None:
    r = results[idx]
    return r if not isinstance(r, Exception) else None


def merge_financial_to_prices(prices: list[dict], financials: dict) -> list[dict]:
    """将最近季度财务数据合并到每条 price 记录中（向前填充）。"""
    from datetime import datetime
    # 取 key_metrics 最近一条作为当前值（财务数据按季度发布）
    metrics = financials.get("key_metrics", [])
    latest_financial = metrics[0] if metrics else {}

    # income
    income = financials.get("income_statement", [])
    latest_income = income[0] if income else {}

    # balance
    balance = financials.get("balance_sheet", [])
    latest_balance = balance[0] if balance else {}

    # cash flow
    cf = financials.get("cash_flow", [])
    latest_cf = cf[0] if cf else {}

    # 合并到每条 price
    result = []
    for p in prices:
        record = dict(p)
        record.update({k: v for k, v in latest_financial.items() if v is not None})
        record.update({k: v for k, v in latest_income.items() if v is not None})
        record.update({k: v for k, v in latest_balance.items() if v is not None})
        record.update({k: v for k, v in latest_cf.items() if v is not None})
        result.append(record)
    return result