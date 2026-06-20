"""标普 500 分析师目标价持续上调筛选服务."""

import asyncio
from datetime import date, timedelta

import httpx

from app.core.logging import logger
from app.schemas.analyst_upgrade import SP500UpgradesResponse, UpgradeStock
from app.services.analyst_upgrade.nasdaq100 import (
    _WIKI_HEADERS,
    _WIKI_RETRIES,
    _compute_recent_points,
    _fetch_constituents_from_wiki,
    _fetch_summary,
    _is_monotonic_up,
    _parse_wiki_html,
    _pct,
)

_WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_WIKI_SP500_API_URL = (
    "https://en.wikipedia.org/w/api.php"
    "?action=parse&page=List_of_S%26P_500_companies&format=json&prop=text&formatversion=2"
)
_CONCURRENCY = 20

# 兜底列表：覆盖标普 500 中分析师覆盖度高的主要成分股
# 已包含纳斯达克 100 重叠成分（AAPL/MSFT 等），以及金融、医疗、能源等独有板块
_FALLBACK_SP500: list[tuple[str, str, str]] = [
    # 科技 / 纳斯达克重叠
    ("AAPL",  "Apple Inc.",                  "Technology"),
    ("MSFT",  "Microsoft Corp.",             "Technology"),
    ("NVDA",  "NVIDIA Corp.",                "Technology"),
    ("AMZN",  "Amazon.com Inc.",             "Consumer Discretionary"),
    ("META",  "Meta Platforms Inc.",         "Communication Services"),
    ("GOOGL", "Alphabet Inc. (A)",           "Communication Services"),
    ("TSLA",  "Tesla Inc.",                  "Consumer Discretionary"),
    ("AVGO",  "Broadcom Inc.",               "Technology"),
    ("AMD",   "Advanced Micro Devices",      "Technology"),
    ("ADBE",  "Adobe Inc.",                  "Technology"),
    ("CRM",   "Salesforce Inc.",             "Technology"),
    ("ORCL",  "Oracle Corp.",                "Technology"),
    ("IBM",   "IBM Corp.",                   "Technology"),
    ("NOW",   "ServiceNow Inc.",             "Technology"),
    ("UBER",  "Uber Technologies",           "Industrials"),
    ("ACN",   "Accenture plc",               "Technology"),
    ("TXN",   "Texas Instruments Inc.",      "Technology"),
    ("QCOM",  "Qualcomm Inc.",               "Technology"),
    ("INTC",  "Intel Corp.",                 "Technology"),
    ("MU",    "Micron Technology Inc.",      "Technology"),
    ("AMAT",  "Applied Materials Inc.",      "Technology"),
    ("LRCX",  "Lam Research Corp.",          "Technology"),
    ("KLAC",  "KLA Corp.",                   "Technology"),
    ("SNPS",  "Synopsys Inc.",               "Technology"),
    ("CDNS",  "Cadence Design Systems",      "Technology"),
    ("FTNT",  "Fortinet Inc.",               "Technology"),
    ("PANW",  "Palo Alto Networks",          "Technology"),
    ("CRWD",  "CrowdStrike Holdings",        "Technology"),
    ("NET",   "Cloudflare Inc.",             "Technology"),
    ("DDOG",  "Datadog Inc.",                "Technology"),
    # 金融
    ("JPM",   "JPMorgan Chase & Co.",        "Financials"),
    ("V",     "Visa Inc.",                   "Financials"),
    ("MA",    "Mastercard Inc.",             "Financials"),
    ("BAC",   "Bank of America Corp.",       "Financials"),
    ("WFC",   "Wells Fargo & Co.",           "Financials"),
    ("GS",    "Goldman Sachs Group",         "Financials"),
    ("MS",    "Morgan Stanley",              "Financials"),
    ("AXP",   "American Express Co.",        "Financials"),
    ("BLK",   "BlackRock Inc.",              "Financials"),
    ("SCHW",  "Charles Schwab Corp.",        "Financials"),
    ("C",     "Citigroup Inc.",              "Financials"),
    ("COF",   "Capital One Financial",       "Financials"),
    ("USB",   "U.S. Bancorp",               "Financials"),
    ("TFC",   "Truist Financial Corp.",      "Financials"),
    ("PNC",   "PNC Financial Services",      "Financials"),
    ("CB",    "Chubb Ltd.",                  "Financials"),
    ("MMC",   "Marsh & McLennan",            "Financials"),
    ("AON",   "Aon plc",                     "Financials"),
    ("ICE",   "Intercontinental Exchange",   "Financials"),
    ("CME",   "CME Group Inc.",              "Financials"),
    ("SPGI",  "S&P Global Inc.",             "Financials"),
    ("MCO",   "Moody's Corp.",               "Financials"),
    ("PYPL",  "PayPal Holdings Inc.",        "Financials"),
    ("COIN",  "Coinbase Global Inc.",        "Financials"),
    # 医疗健康
    ("UNH",   "UnitedHealth Group",          "Health Care"),
    ("LLY",   "Eli Lilly and Co.",           "Health Care"),
    ("JNJ",   "Johnson & Johnson",           "Health Care"),
    ("ABBV",  "AbbVie Inc.",                 "Health Care"),
    ("MRK",   "Merck & Co. Inc.",            "Health Care"),
    ("PFE",   "Pfizer Inc.",                 "Health Care"),
    ("TMO",   "Thermo Fisher Scientific",    "Health Care"),
    ("ABT",   "Abbott Laboratories",         "Health Care"),
    ("DHR",   "Danaher Corp.",               "Health Care"),
    ("SYK",   "Stryker Corp.",               "Health Care"),
    ("BSX",   "Boston Scientific Corp.",     "Health Care"),
    ("ELV",   "Elevance Health Inc.",        "Health Care"),
    ("CVS",   "CVS Health Corp.",            "Health Care"),
    ("CI",    "Cigna Group",                 "Health Care"),
    ("HCA",   "HCA Healthcare Inc.",         "Health Care"),
    ("MDT",   "Medtronic plc",               "Health Care"),
    ("ISRG",  "Intuitive Surgical Inc.",     "Health Care"),
    ("AMGN",  "Amgen Inc.",                  "Health Care"),
    ("GILD",  "Gilead Sciences Inc.",        "Health Care"),
    ("REGN",  "Regeneron Pharma.",           "Health Care"),
    ("VRTX",  "Vertex Pharmaceuticals",      "Health Care"),
    ("BIIB",  "Biogen Inc.",                 "Health Care"),
    # 消费品 / 零售
    ("WMT",   "Walmart Inc.",                "Consumer Staples"),
    ("COST",  "Costco Wholesale Corp.",      "Consumer Staples"),
    ("PG",    "Procter & Gamble Co.",        "Consumer Staples"),
    ("KO",    "Coca-Cola Co.",               "Consumer Staples"),
    ("PEP",   "PepsiCo Inc.",               "Consumer Staples"),
    ("PM",    "Philip Morris International", "Consumer Staples"),
    ("MO",    "Altria Group Inc.",           "Consumer Staples"),
    ("MDLZ",  "Mondelez International",      "Consumer Staples"),
    ("CL",    "Colgate-Palmolive Co.",       "Consumer Staples"),
    ("KMB",   "Kimberly-Clark Corp.",        "Consumer Staples"),
    ("HD",    "Home Depot Inc.",             "Consumer Discretionary"),
    ("MCD",   "McDonald's Corp.",            "Consumer Discretionary"),
    ("NKE",   "Nike Inc.",                   "Consumer Discretionary"),
    ("SBUX",  "Starbucks Corp.",             "Consumer Discretionary"),
    ("TGT",   "Target Corp.",               "Consumer Discretionary"),
    ("LOW",   "Lowe's Companies Inc.",       "Consumer Discretionary"),
    ("BKNG",  "Booking Holdings Inc.",       "Consumer Discretionary"),
    ("MAR",   "Marriott International",      "Consumer Discretionary"),
    # 工业
    ("CAT",   "Caterpillar Inc.",            "Industrials"),
    ("HON",   "Honeywell International",     "Industrials"),
    ("DE",    "Deere & Co.",                 "Industrials"),
    ("RTX",   "RTX Corp.",                   "Industrials"),
    ("LMT",   "Lockheed Martin Corp.",       "Industrials"),
    ("GE",    "GE Aerospace",                "Industrials"),
    ("BA",    "Boeing Co.",                  "Industrials"),
    ("UPS",   "United Parcel Service",       "Industrials"),
    ("FDX",   "FedEx Corp.",                 "Industrials"),
    ("MMM",   "3M Co.",                      "Industrials"),
    ("EMR",   "Emerson Electric Co.",        "Industrials"),
    ("ETN",   "Eaton Corp. plc",             "Industrials"),
    ("ITW",   "Illinois Tool Works",         "Industrials"),
    ("PH",    "Parker-Hannifin Corp.",       "Industrials"),
    ("GD",    "General Dynamics Corp.",      "Industrials"),
    ("NOC",   "Northrop Grumman Corp.",      "Industrials"),
    ("CTAS",  "Cintas Corp.",                "Industrials"),
    # 能源
    ("XOM",   "Exxon Mobil Corp.",           "Energy"),
    ("CVX",   "Chevron Corp.",               "Energy"),
    ("COP",   "ConocoPhillips",              "Energy"),
    ("EOG",   "EOG Resources Inc.",          "Energy"),
    ("SLB",   "Schlumberger Ltd.",           "Energy"),
    ("OXY",   "Occidental Petroleum",        "Energy"),
    ("MPC",   "Marathon Petroleum Corp.",    "Energy"),
    ("PSX",   "Phillips 66",                 "Energy"),
    # 通信
    ("VZ",    "Verizon Communications",      "Communication Services"),
    ("T",     "AT&T Inc.",                   "Communication Services"),
    ("NFLX",  "Netflix Inc.",                "Communication Services"),
    ("DIS",   "Walt Disney Co.",             "Communication Services"),
    ("CMCSA", "Comcast Corp.",               "Communication Services"),
    # 公用事业
    ("NEE",   "NextEra Energy Inc.",         "Utilities"),
    ("SO",    "Southern Co.",                "Utilities"),
    ("DUK",   "Duke Energy Corp.",           "Utilities"),
    ("CEG",   "Constellation Energy",        "Utilities"),
    ("VST",   "Vistra Corp.",                "Utilities"),
    # 房地产
    ("PLD",   "Prologis Inc.",               "Real Estate"),
    ("AMT",   "American Tower Corp.",        "Real Estate"),
    ("EQIX",  "Equinix Inc.",               "Real Estate"),
    ("SPG",   "Simon Property Group",        "Real Estate"),
    ("WELL",  "Welltower Inc.",              "Real Estate"),
    # 材料
    ("LIN",   "Linde plc",                   "Materials"),
    ("APD",   "Air Products & Chemicals",    "Materials"),
    ("NEM",   "Newmont Corp.",               "Materials"),
    ("FCX",   "Freeport-McMoRan Inc.",       "Materials"),
    ("SHW",   "Sherwin-Williams Co.",        "Materials"),
]


def _fallback_sp500() -> list[dict]:
    return [
        {"symbol": sym, "name": name, "sector": sector}
        for sym, name, sector in _FALLBACK_SP500
    ]


async def _fetch_sp500_via_article(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        _WIKI_SP500_URL, headers=_WIKI_HEADERS, timeout=20, follow_redirects=True
    )
    if resp.status_code != 200:
        logger.warning("wiki_sp500_article_http_error", status=resp.status_code)
        return []
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None, _parse_wiki_html, resp.text
    )


async def _fetch_sp500_via_api(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        _WIKI_SP500_API_URL, headers=_WIKI_HEADERS, timeout=20, follow_redirects=True
    )
    if resp.status_code != 200:
        logger.warning("wiki_sp500_api_http_error", status=resp.status_code)
        return []
    html = resp.json().get("parse", {}).get("text", "")
    if not html:
        return []
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None, _parse_wiki_html, html
    )


async def _fetch_sp500_constituents(client: httpx.AsyncClient) -> list[dict]:
    """从 Wikipedia 动态拉取标普 500 成分股，失败时降级兜底列表."""
    sources = (
        ("article", _fetch_sp500_via_article),
        ("api", _fetch_sp500_via_api),
    )
    for source_name, fetcher in sources:
        for attempt in range(1, _WIKI_RETRIES + 1):
            try:
                constituents = await fetcher(client)
                if len(constituents) >= 450:
                    logger.info(
                        "wiki_sp500_fetched",
                        count=len(constituents),
                        source=source_name,
                        attempt=attempt,
                    )
                    return constituents
                if constituents:
                    logger.warning(
                        "wiki_sp500_too_few",
                        count=len(constituents),
                        source=source_name,
                        attempt=attempt,
                    )
            except Exception as e:
                logger.warning(
                    "wiki_sp500_fetch_failed",
                    error=str(e),
                    source=source_name,
                    attempt=attempt,
                )
            if attempt < _WIKI_RETRIES:
                await asyncio.sleep(2 ** attempt)

    logger.warning("sp500_constituent_using_fallback_list")
    return _fallback_sp500()


async def compute_sp500_upgrades() -> SP500UpgradesResponse:
    """拉取标普 500 成分股，筛选目标价三层单调递增的股票."""
    async with httpx.AsyncClient(timeout=30) as client:
        constituents = await _fetch_sp500_constituents(client)

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

    if stocks:
        cutoff_18m = date.today() - timedelta(days=548)
        sem2 = asyncio.Semaphore(10)
        async with httpx.AsyncClient(timeout=30) as client2:
            history_pairs = await asyncio.gather(
                *[_compute_recent_points(client2, s.symbol, sem2, cutoff_18m) for s in stocks]
            )
        history_map = dict(history_pairs)
        for stock in stocks:
            stock.recent_points = history_map.get(stock.symbol, [])

    logger.info(
        "sp500_upgrades_computed",
        total=len(constituents),
        qualifying=len(stocks),
    )

    return SP500UpgradesResponse(
        as_of=date.today().isoformat(),
        total_constituents=len(constituents),
        upgrade_count=len(stocks),
        stocks=stocks,
    )
