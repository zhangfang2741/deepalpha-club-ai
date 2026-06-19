"""纳斯达克 100 分析师目标价上调筛选服务."""

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import StringIO

import httpx
import pandas as pd

from app.core.config import settings
from app.core.logging import logger
from app.schemas.analyst_upgrade import (
    Nasdaq100UpgradesResponse,
    PriceTargetHistoryResponse,
    PriceTargetPoint,
    UpgradeStock,
)

_FMP_STABLE = "https://financialmodelingprep.com/stable"
_CONCURRENCY = 20
_WIKI_NDX_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
# Wikipedia 官方 action API：返回 JSON 包裹的渲染 HTML，比直接爬文章页更适合程序化访问
_WIKI_API_URL = (
    "https://en.wikipedia.org/w/api.php"
    "?action=parse&page=Nasdaq-100&format=json&prop=text&formatversion=2"
)
# 使用浏览器级别的 User-Agent，避免被 Wikipedia 拦截
_WIKI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_WIKI_RETRIES = 3

# 兜底成分股列表：当 Wikipedia 和 FMP 均不可用时使用
# 最后更新：2025-06，对照官方 Nasdaq-100 成分股名单校准
# 已移除：ENPH（2022-12）、ILMN（2023-12）、DOCU（2023-06）、
#         WBD（2024-06）、SNDK（分拆新股，FMP 数据继承 WDC 历史目标价，失真）
# 格式：(symbol, name, sector)
_FALLBACK_NDX100: list[tuple[str, str, str]] = [
    ("AAPL",  "Apple Inc.",              "Technology"),
    ("MSFT",  "Microsoft Corp.",         "Technology"),
    ("NVDA",  "NVIDIA Corp.",            "Technology"),
    ("AMZN",  "Amazon.com Inc.",         "Consumer Cyclical"),
    ("META",  "Meta Platforms Inc.",     "Communication Services"),
    ("GOOGL", "Alphabet Inc. (A)",       "Communication Services"),
    ("GOOG",  "Alphabet Inc. (C)",       "Communication Services"),
    ("TSLA",  "Tesla Inc.",              "Consumer Cyclical"),
    ("AVGO",  "Broadcom Inc.",           "Technology"),
    ("COST",  "Costco Wholesale Corp.",  "Consumer Defensive"),
    ("NFLX",  "Netflix Inc.",            "Communication Services"),
    ("ARM",   "Arm Holdings plc",        "Technology"),
    ("ASML",  "ASML Holding NV",         "Technology"),
    ("AMD",   "Advanced Micro Devices",  "Technology"),
    ("AZN",   "AstraZeneca PLC",         "Healthcare"),
    ("CSCO",  "Cisco Systems Inc.",      "Technology"),
    ("ADBE",  "Adobe Inc.",              "Technology"),
    ("QCOM",  "Qualcomm Inc.",           "Technology"),
    ("INTU",  "Intuit Inc.",             "Technology"),
    ("TXN",   "Texas Instruments Inc.",  "Technology"),
    ("AMGN",  "Amgen Inc.",              "Healthcare"),
    ("ISRG",  "Intuitive Surgical Inc.", "Healthcare"),
    ("BKNG",  "Booking Holdings Inc.",   "Consumer Cyclical"),
    ("AMAT",  "Applied Materials Inc.",  "Technology"),
    ("LRCX",  "Lam Research Corp.",      "Technology"),
    ("MU",    "Micron Technology Inc.",  "Technology"),
    ("ADI",   "Analog Devices Inc.",     "Technology"),
    ("PANW",  "Palo Alto Networks Inc.", "Technology"),
    ("REGN",  "Regeneron Pharma.",       "Healthcare"),
    ("VRTX",  "Vertex Pharmaceuticals",  "Healthcare"),
    ("GILD",  "Gilead Sciences Inc.",    "Healthcare"),
    ("KLAC",  "KLA Corp.",               "Technology"),
    ("SNPS",  "Synopsys Inc.",           "Technology"),
    ("CDNS",  "Cadence Design Systems",  "Technology"),
    ("MRVL",  "Marvell Technology Inc.", "Technology"),
    ("MELI",  "MercadoLibre Inc.",       "Consumer Cyclical"),
    ("FTNT",  "Fortinet Inc.",           "Technology"),
    ("MNST",  "Monster Beverage Corp.",  "Consumer Defensive"),
    ("NXPI",  "NXP Semiconductors NV",  "Technology"),
    ("DXCM",  "DexCom Inc.",             "Healthcare"),
    ("CRWD",  "CrowdStrike Holdings",    "Technology"),
    ("SMCI",  "Super Micro Computer",    "Technology"),
    ("KDP",   "Keurig Dr Pepper Inc.",   "Consumer Defensive"),
    ("PCAR",  "PACCAR Inc.",             "Industrials"),
    ("MDLZ",  "Mondelez International",  "Consumer Defensive"),
    ("ORLY",  "O'Reilly Automotive",     "Consumer Cyclical"),
    ("ADP",   "Automatic Data Processing","Technology"),
    ("CSGP",  "CoStar Group Inc.",       "Real Estate"),
    ("ABNB",  "Airbnb Inc.",             "Consumer Cyclical"),
    ("PYPL",  "PayPal Holdings Inc.",    "Financial Services"),
    ("CHTR",  "Charter Communications",  "Communication Services"),
    ("MAR",   "Marriott International",  "Consumer Cyclical"),
    ("ROP",   "Roper Technologies Inc.", "Technology"),
    ("BIIB",  "Biogen Inc.",             "Healthcare"),
    ("WDAY",  "Workday Inc.",            "Technology"),
    ("VRSK",  "Verisk Analytics Inc.",   "Industrials"),
    ("FAST",  "Fastenal Co.",            "Industrials"),
    ("CPRT",  "Copart Inc.",             "Industrials"),
    ("PAYX",  "Paychex Inc.",            "Technology"),
    ("IDXX",  "IDEXX Laboratories",      "Healthcare"),
    ("TEAM",  "Atlassian Corp.",         "Technology"),
    ("DLTR",  "Dollar Tree Inc.",        "Consumer Defensive"),
    ("ODFL",  "Old Dominion Freight",    "Industrials"),
    ("TTWO",  "Take-Two Interactive",    "Communication Services"),
    ("ZS",    "Zscaler Inc.",            "Technology"),
    ("ALGN",  "Align Technology Inc.",   "Healthcare"),
    ("GEHC",  "GE HealthCare Tech.",     "Healthcare"),
    ("ON",    "ON Semiconductor Corp.",  "Technology"),
    ("LULU",  "Lululemon Athletica",     "Consumer Cyclical"),
    ("SBUX",  "Starbucks Corp.",         "Consumer Cyclical"),
    ("CMCSA", "Comcast Corp.",           "Communication Services"),
    ("HON",   "Honeywell International", "Industrials"),
    ("EA",    "Electronic Arts Inc.",    "Communication Services"),
    ("EBAY",  "eBay Inc.",               "Consumer Cyclical"),
    ("XEL",   "Xcel Energy Inc.",        "Utilities"),
    ("ANSS",  "Ansys Inc.",              "Technology"),
    ("OKTA",  "Okta Inc.",               "Technology"),
    ("DDOG",  "Datadog Inc.",            "Technology"),
    ("INTC",  "Intel Corp.",             "Technology"),
    ("WDC",   "Western Digital Corp.",   "Technology"),
    ("STX",   "Seagate Technology",      "Technology"),
    ("CEG",   "Constellation Energy",    "Utilities"),
    ("MCHP",  "Microchip Technology",    "Technology"),
    ("PDD",   "PDD Holdings Inc.",       "Consumer Cyclical"),
    ("JD",    "JD.com Inc.",             "Consumer Cyclical"),
    ("FANG",  "Diamondback Energy",      "Energy"),
    ("ZM",    "Zoom Video Comm.",        "Technology"),
    ("SNOW",  "Snowflake Inc.",          "Technology"),
    ("HOOD",  "Robinhood Markets",       "Financial Services"),
    ("APP",   "Applovin Corp.",          "Technology"),
    ("PLTR",  "Palantir Technologies",   "Technology"),
    ("TTD",   "The Trade Desk Inc.",     "Technology"),
    ("CTAS",  "Cintas Corp.",            "Industrials"),
    ("TTWO",  "Take-Two Interactive",    "Communication Services"),
]


def _fallback_constituents() -> list[dict]:
    return [
        {"symbol": sym, "name": name, "sector": sector}
        for sym, name, sector in _FALLBACK_NDX100
    ]


def _parse_wiki_html(html: str) -> list[dict]:
    """从 Wikipedia HTML 中解析纳斯达克 100 成分股表格."""
    tables = pd.read_html(StringIO(html))
    for table in tables:
        cols = [str(c).strip() for c in table.columns]
        # 找到含有 Ticker 列的表格
        ticker_col = next((c for c in cols if "ticker" in c.lower() or "symbol" in c.lower()), None)
        if ticker_col is None:
            continue
        name_col = next((c for c in cols if "company" in c.lower() or "name" in c.lower()), None)
        sector_col = next((c for c in cols if "sector" in c.lower() or "gics" in c.lower()), None)
        result = []
        for _, row in table.iterrows():
            sym = str(row[ticker_col]).strip()
            if not sym or sym == "nan":
                continue
            result.append({
                "symbol": sym,
                "name": str(row[name_col]).strip() if name_col else sym,
                "sector": str(row[sector_col]).strip() if sector_col else "",
            })
        if len(result) >= 90:
            return result
    return []


async def _fetch_wiki_via_article(client: httpx.AsyncClient) -> list[dict]:
    """直接抓取 Wikipedia 文章页 HTML 并解析."""
    resp = await client.get(
        _WIKI_NDX_URL, headers=_WIKI_HEADERS, timeout=20, follow_redirects=True
    )
    if resp.status_code != 200:
        logger.warning("wiki_article_http_error", status=resp.status_code)
        return []
    return await asyncio.get_event_loop().run_in_executor(
        None, _parse_wiki_html, resp.text
    )


async def _fetch_wiki_via_api(client: httpx.AsyncClient) -> list[dict]:
    """通过 Wikipedia 官方 action API 拉取渲染后的 HTML 并解析."""
    resp = await client.get(
        _WIKI_API_URL, headers=_WIKI_HEADERS, timeout=20, follow_redirects=True
    )
    if resp.status_code != 200:
        logger.warning("wiki_api_http_error", status=resp.status_code)
        return []
    html = resp.json().get("parse", {}).get("text", "")
    if not html:
        return []
    return await asyncio.get_event_loop().run_in_executor(
        None, _parse_wiki_html, html
    )


async def _fetch_constituents_from_wiki(client: httpx.AsyncClient) -> list[dict]:
    """从 Wikipedia 动态拉取纳斯达克 100 成分股.

    依次尝试文章页和官方 API 两种来源，每种来源失败时按指数退避重试.
    """
    sources = (
        ("article", _fetch_wiki_via_article),
        ("api", _fetch_wiki_via_api),
    )
    for source_name, fetcher in sources:
        for attempt in range(1, _WIKI_RETRIES + 1):
            try:
                constituents = await fetcher(client)
                if constituents:
                    logger.info(
                        "wiki_ndx100_fetched",
                        count=len(constituents),
                        source=source_name,
                        attempt=attempt,
                    )
                    return constituents
                logger.warning(
                    "wiki_ndx100_parse_empty", source=source_name, attempt=attempt
                )
            except Exception as e:
                logger.warning(
                    "wiki_ndx100_fetch_failed",
                    error=str(e),
                    source=source_name,
                    attempt=attempt,
                )
            if attempt < _WIKI_RETRIES:
                await asyncio.sleep(2 ** attempt)
    return []


async def _fetch_constituents(client: httpx.AsyncClient) -> list[dict]:
    """获取纳斯达克 100 成分股：Wikipedia 动态拉取，失败时降级兜底列表."""
    constituents = await _fetch_constituents_from_wiki(client)
    if constituents:
        return constituents

    logger.warning("nasdaq_constituent_using_fallback_list")
    return _fallback_constituents()


async def _fetch_summary(client: httpx.AsyncClient, symbol: str) -> dict | None:
    resp = await client.get(
        f"{_FMP_STABLE}/price-target-summary",
        params={"symbol": symbol, "apikey": settings.FMP_API_KEY},
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data[0] if isinstance(data, list) and data else None


def _is_monotonic_up(s: dict) -> bool:
    m = s.get("lastMonthAvgPriceTarget") or 0
    q = s.get("lastQuarterAvgPriceTarget") or 0
    y = s.get("lastYearAvgPriceTarget") or 0
    mc = s.get("lastMonthCount") or 0
    return mc >= 2 and m > 0 and q > 0 and y > 0 and m > q > y


def _pct(new: float, old: float) -> float:
    if not old:
        return 0.0
    return round((new - old) / old * 100, 1)


async def compute_nasdaq100_upgrades() -> Nasdaq100UpgradesResponse:
    """拉取纳斯达克 100 成分股，筛选目标价三层单调递增的股票."""
    async with httpx.AsyncClient(timeout=30) as client:
        constituents = await _fetch_constituents(client)

        name_map = {c["symbol"]: c.get("name", c["symbol"]) for c in constituents}
        sector_map = {c["symbol"]: c.get("sector", "") for c in constituents}
        symbols = list(name_map.keys())

        sem = asyncio.Semaphore(_CONCURRENCY)

        async def fetch_one(sym: str) -> tuple[str, dict | None]:
            async with sem:
                return sym, await _fetch_summary(client, sym)

        results = await asyncio.gather(*[fetch_one(s) for s in symbols])

    stocks: list[UpgradeStock] = []
    for sym, summary in results:
        if not summary or not _is_monotonic_up(summary):
            continue

        m = summary["lastMonthAvgPriceTarget"]
        q = summary["lastQuarterAvgPriceTarget"]
        y = summary["lastYearAvgPriceTarget"]
        at = summary.get("allTimeAvgPriceTarget") or 0

        stocks.append(UpgradeStock(
            symbol=sym,
            name=name_map.get(sym, sym),
            sector=sector_map.get(sym, ""),
            last_month_target=round(m, 2),
            last_quarter_target=round(q, 2),
            last_year_target=round(y, 2),
            all_time_target=round(at, 2),
            last_month_count=summary.get("lastMonthCount") or 0,
            month_mom=_pct(m, q),
            quarter_yoy=_pct(q, y),
            year_vs_all=_pct(y, at) if at else 0.0,
        ))

    stocks.sort(key=lambda s: s.month_mom, reverse=True)

    logger.info(
        "nasdaq100_upgrades_computed",
        total=len(constituents),
        qualifying=len(stocks),
    )

    return Nasdaq100UpgradesResponse(
        as_of=date.today().isoformat(),
        total_constituents=len(constituents),
        upgrade_count=len(stocks),
        stocks=stocks,
    )


# 逐条目标价端点候选：stable price-target-news 为正确历史端点，依次降级 v4 / stable price-target
_FMP_PT_URLS = (
    f"{_FMP_STABLE}/price-target-news",
    "https://financialmodelingprep.com/api/v4/price-target",
    f"{_FMP_STABLE}/price-target",
)
# 不同端点/版本的字段名差异，做兼容
_PT_DATE_FIELDS = ("publishedDate", "date", "published_date", "datePublished", "publishedAt")
_PT_VALUE_FIELDS = ("priceTarget", "adjPriceTarget", "price_target")


def _extract_pt_date(rec: dict) -> date | None:
    for k in _PT_DATE_FIELDS:
        v = rec.get(k)
        if v:
            try:
                return datetime.fromisoformat(str(v)[:10]).date()
            except ValueError:
                continue
    return None


def _extract_pt_value(rec: dict) -> float | None:
    for k in _PT_VALUE_FIELDS:
        v = rec.get(k)
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


async def _fetch_price_target_records(client: httpx.AsyncClient, symbol: str) -> list[dict]:
    """逐条拉取个股分析师目标价记录，依次尝试多个端点，命中即返回."""
    for url in _FMP_PT_URLS:
        records: list[dict] = []
        for page in range(20):
            try:
                resp = await client.get(
                    url,
                    params={
                        "symbol": symbol.upper(),
                        "page": page,
                        "limit": 100,
                        "apikey": settings.FMP_API_KEY,
                    },
                )
            except Exception as e:
                logger.warning("price_target_fetch_error", symbol=symbol, url=url, error=str(e))
                break
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            records.extend(batch)
            # 单次返回不足一页说明已到末尾（或该端点不分页）
            if len(batch) < 100:
                break
        if records:
            logger.info("price_target_records_fetched", symbol=symbol, url=url, count=len(records))
            return records
    logger.warning("price_target_records_empty", symbol=symbol)
    return []


async def compute_price_target_history(symbol: str) -> PriceTargetHistoryResponse:
    """拉取个股近 5 年分析师目标价，按月聚合均值."""
    cutoff = date.today() - timedelta(days=5 * 365)
    monthly: dict[str, list[float]] = defaultdict(list)

    async with httpx.AsyncClient(timeout=30) as client:
        records = await _fetch_price_target_records(client, symbol)

    for rec in records:
        dt = _extract_pt_date(rec)
        pt = _extract_pt_value(rec)
        if dt is None or pt is None or dt < cutoff:
            continue
        monthly[f"{dt.year}-{dt.month:02d}"].append(pt)

    points: list[PriceTargetPoint] = [
        PriceTargetPoint(
            label=label,
            avg_target=round(sum(vals) / len(vals), 2),
            count=len(vals),
        )
        for label, vals in monthly.items()
        if vals
    ]
    points.sort(key=lambda p: p.label)

    logger.info("price_target_history_computed", symbol=symbol, months=len(points))

    return PriceTargetHistoryResponse(symbol=symbol.upper(), points=points)
