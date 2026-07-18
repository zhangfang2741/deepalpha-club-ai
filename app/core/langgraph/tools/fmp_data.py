"""FMP 数据查询工具集：把 FMP（Financial Modeling Prep）行情/基本面/财务数据封装为 Agent 工具。

复用 app.services.analyzer.fmp_client.FmpClient（stable API + 优雅降级）。每次调用使用独立
client 实例，避免跨调用缓存导致行情陈旧。返回精炼的中文 Markdown，而非原始 JSON，以控制上下文体积。
"""

from typing import Any, Callable, Optional

from langchain_core.tools import tool

from app.services.analyzer.fmp_client import FmpClient


def _fmt_money(value: Any) -> Optional[str]:
    """把数值格式化为 $xxB / $xxM / $xxK / $xx。"""
    if not isinstance(value, (int, float)) or value == 0:
        return None
    av = abs(value)
    if av >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if av >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if av >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if av >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:.2f}"


def _fmt_ratio(value: Any) -> Optional[str]:
    """保留两位小数的比率（如 PE、PB、beta）。"""
    if not isinstance(value, (int, float)):
        return None
    return f"{value:.2f}"


def _fmt_pct(value: Any) -> Optional[str]:
    """把小数比率格式化为百分比（0.653 → 65.3%）。"""
    if not isinstance(value, (int, float)):
        return None
    return f"{value * 100:.2f}%"


def _fmt_raw(value: Any) -> Optional[str]:
    """字符串/原样输出，空值返回 None。"""
    if value is None or value == "":
        return None
    return str(value)


def _first(record: Any) -> dict:
    """FMP 返回 list 或 dict，统一取第一条 dict。"""
    if isinstance(record, list):
        return record[0] if record else {}
    if isinstance(record, dict):
        return record
    return {}


def _pick(source: dict, key: str, *fallbacks: str) -> Any:
    """按主键 + 回退键取值（兼容 FMP 不同版本字段名）。"""
    for k in (key, *fallbacks):
        if k in source and source[k] not in (None, ""):
            return source[k]
    return None


def _kv_table(rows: list[tuple[str, Optional[str]]]) -> str:
    """把 (标签, 值) 列表渲染为两列 Markdown 表格，跳过空值。"""
    kept = [(label, val) for label, val in rows if val is not None]
    if not kept:
        return ""
    lines = ["| 指标 | 数据 |", "|------|------|"]
    lines += [f"| {label} | {val} |" for label, val in kept]
    return "\n".join(lines)


@tool
async def fmp_quote(symbol: str) -> str:
    """查询美股实时报价（价格、涨跌幅、市值、市盈率、成交量、52周范围、均线等）。

    当用户想了解某只股票"现在多少钱""市值多大""估值高不高"等即时行情时使用。数据来自 FMP。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA'、'TSLA'（美股）

    Returns:
        Markdown 格式的实时报价摘要；无数据时返回提示。
    """
    client = FmpClient()
    q = _first(await client.get_price_data(symbol))
    if not q:
        return f"未获取到 {symbol.upper()} 的报价数据（可能是代码有误或 FMP_API_KEY 未配置）。"

    year_low = _pick(q, "yearLow")
    year_high = _pick(q, "yearHigh")
    year_range = f"${year_low} – ${year_high}" if year_low and year_high else None

    table = _kv_table(
        [
            ("名称", _fmt_raw(_pick(q, "name"))),
            ("当前价格", _fmt_money(_pick(q, "price"))),
            ("涨跌幅", _fmt_pct_change(_pick(q, "changePercentage", "changesPercentage"))),
            ("市值", _fmt_money(_pick(q, "marketCap"))),
            ("市盈率(PE)", _fmt_ratio(_pick(q, "pe"))),
            ("每股收益(EPS)", _fmt_ratio(_pick(q, "eps"))),
            ("成交量", _fmt_raw(_pick(q, "volume"))),
            ("日内区间", _day_range(q)),
            ("52周范围", year_range),
            ("50日均价", _fmt_money(_pick(q, "priceAvg50"))),
            ("200日均价", _fmt_money(_pick(q, "priceAvg200"))),
            ("交易所", _fmt_raw(_pick(q, "exchange"))),
        ]
    )
    return f"### {symbol.upper()} 实时报价\n\n{table}\n\n> 数据来源：FMP"


def _fmt_pct_change(value: Any) -> Optional[str]:
    """涨跌幅本身已是百分比数值（如 -1.23 表示 -1.23%）。"""
    if not isinstance(value, (int, float)):
        return None
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _day_range(q: dict) -> Optional[str]:
    low = _pick(q, "dayLow")
    high = _pick(q, "dayHigh")
    if low and high:
        return f"${low} – ${high}"
    return None


@tool
async def fmp_company_profile(symbol: str) -> str:
    """查询公司画像（所属行业/板块、市值、Beta、CEO、员工数、简介、官网等）。

    当用户想了解"这家公司是做什么的""属于哪个行业""基本情况"时使用。数据来自 FMP。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA'

    Returns:
        Markdown 格式的公司画像摘要；无数据时返回提示。
    """
    client = FmpClient()
    p = _first(await client.get_company_profile(symbol))
    if not p:
        return f"未获取到 {symbol.upper()} 的公司画像（可能是代码有误或 FMP_API_KEY 未配置）。"

    desc = _pick(p, "description")
    if isinstance(desc, str) and len(desc) > 400:
        desc = desc[:400] + "…"

    table = _kv_table(
        [
            ("公司名称", _fmt_raw(_pick(p, "companyName"))),
            ("板块", _fmt_raw(_pick(p, "sector"))),
            ("行业", _fmt_raw(_pick(p, "industry"))),
            ("市值", _fmt_money(_pick(p, "marketCap"))),
            ("当前价格", _fmt_money(_pick(p, "price"))),
            ("Beta", _fmt_ratio(_pick(p, "beta"))),
            ("CEO", _fmt_raw(_pick(p, "ceo"))),
            ("员工数", _fmt_raw(_pick(p, "fullTimeEmployees"))),
            ("国家", _fmt_raw(_pick(p, "country"))),
            ("交易所", _fmt_raw(_pick(p, "exchangeFullName", "exchange"))),
            ("官网", _fmt_raw(_pick(p, "website"))),
        ]
    )
    parts = [f"### {symbol.upper()} 公司画像", "", table]
    if desc:
        parts += ["", "**简介**", "", str(desc)]
    parts += ["", "> 数据来源：FMP"]
    return "\n".join(parts)


# 各类财务报表的关键行项目（标签, 主键, *回退键）
_STATEMENT_FIELDS: dict[str, list[tuple[str, str, tuple[str, ...]]]] = {
    "income": [
        ("营收", "revenue", ()),
        ("毛利", "grossProfit", ()),
        ("营业利润", "operatingIncome", ()),
        ("净利润", "netIncome", ()),
        ("EPS(摊薄)", "epsdiluted", ("epsDiluted", "eps")),
        ("EBITDA", "ebitda", ()),
    ],
    "balance": [
        ("总资产", "totalAssets", ()),
        ("总负债", "totalLiabilities", ()),
        ("股东权益", "totalStockholdersEquity", ("totalEquity",)),
        ("现金及等价物", "cashAndCashEquivalents", ()),
        ("总债务", "totalDebt", ()),
    ],
    "cashflow": [
        ("经营现金流", "operatingCashFlow", ("netCashProvidedByOperatingActivities",)),
        ("自由现金流", "freeCashFlow", ()),
        ("资本开支", "capitalExpenditure", ()),
    ],
}

_STATEMENT_FETCHERS: dict[str, tuple[str, Callable[[FmpClient, str, int], Any]]] = {
    "income": ("利润表", lambda c, s, n: c.get_income_statement(s, limit=n)),
    "balance": ("资产负债表", lambda c, s, n: c.get_balance_sheet(s, limit=n)),
    "cashflow": ("现金流量表", lambda c, s, n: c.get_cash_flow(s, limit=n)),
}


@tool
async def fmp_financial_statement(symbol: str, statement: str = "income", limit: int = 4) -> str:
    """查询公司财务报表（利润表 / 资产负债表 / 现金流量表），按期对比关键科目。

    当用户想看"营收/净利润趋势""现金流""资产负债结构"等财务数据时使用。数据来自 FMP。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA'
        statement: 报表类型，income（利润表，默认）/ balance（资产负债表）/ cashflow（现金流量表）
        limit: 拉取最近几个报告期（默认 4，最多 8）

    Returns:
        Markdown 表格：行=关键科目，列=各报告期；无数据时返回提示。
    """
    key = statement.strip().lower()
    if key not in _STATEMENT_FETCHERS:
        return "statement 参数无效，应为 income / balance / cashflow 之一。"
    limit = max(1, min(limit, 8))

    title, fetcher = _STATEMENT_FETCHERS[key]
    client = FmpClient()
    records = await fetcher(client, symbol, limit)
    if not isinstance(records, list) or not records:
        return f"未获取到 {symbol.upper()} 的{title}数据（可能是代码有误或 FMP_API_KEY 未配置）。"

    periods = [str(_pick(r, "date", "calendarYear") or "?") for r in records]
    header = "| 科目 | " + " | ".join(periods) + " |"
    divider = "|------|" + "|".join(["------"] * len(periods)) + "|"
    lines = [header, divider]
    for label, primary, fallbacks in _STATEMENT_FIELDS[key]:
        cells = []
        for r in records:
            val = _pick(r, primary, *fallbacks)
            if label.startswith("EPS"):
                cells.append(_fmt_ratio(val) or "—")
            else:
                cells.append(_fmt_money(val) or "—")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    body = "\n".join(lines)
    return f"### {symbol.upper()} {title}（最近 {len(periods)} 期）\n\n{body}\n\n> 数据来源：FMP"


@tool
async def fmp_key_metrics(symbol: str, limit: int = 1) -> str:
    """查询公司关键财务指标与估值/盈利比率（PE、PB、ROE、各项利润率、负债率、股息率等）。

    当用户想判断"估值贵不贵""盈利质量如何""财务是否健康"时使用。综合 FMP 的 key-metrics 与 ratios。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA'
        limit: 拉取最近几期用于取最新一期（默认 1）

    Returns:
        Markdown 表格：估值 / 盈利 / 财务健康关键指标；无数据时返回提示。
    """
    client = FmpClient()
    metrics = _first(await client.get_key_metrics(symbol, limit=max(1, limit)))
    ratios = _first(await client.get_financial_ratios(symbol, limit=max(1, limit)))
    if not metrics and not ratios:
        return f"未获取到 {symbol.upper()} 的关键指标（可能是代码有误或 FMP_API_KEY 未配置）。"

    table = _kv_table(
        [
            ("市盈率(PE)", _fmt_ratio(_pick(ratios, "priceToEarningsRatio", "peRatio"))),
            ("市净率(PB)", _fmt_ratio(_pick(ratios, "priceToBookRatio", "pbRatio"))),
            ("市销率(PS)", _fmt_ratio(_pick(ratios, "priceToSalesRatio"))),
            ("毛利率", _fmt_pct(_pick(ratios, "grossProfitMargin"))),
            ("净利率", _fmt_pct(_pick(ratios, "netProfitMargin"))),
            ("ROE", _fmt_pct(_pick(ratios, "returnOnEquity"))),
            ("ROA", _fmt_pct(_pick(ratios, "returnOnAssets"))),
            ("流动比率", _fmt_ratio(_pick(ratios, "currentRatio"))),
            ("负债权益比", _fmt_ratio(_pick(ratios, "debtToEquityRatio", "debtToEquity"))),
            ("股息率", _fmt_pct(_pick(ratios, "dividendYield"))),
            ("每股自由现金流", _fmt_ratio(_pick(metrics, "freeCashFlowPerShare"))),
            ("企业价值(EV)", _fmt_money(_pick(metrics, "enterpriseValue"))),
        ]
    )
    return f"### {symbol.upper()} 关键指标与估值\n\n{table}\n\n> 数据来源：FMP"
