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
    PriceTargetQuarter,
    UpgradeStock,
)

_FMP_STABLE = "https://financialmodelingprep.com/stable"
_FMP_V3 = "https://financialmodelingprep.com/api/v3"
_CONCURRENCY = 20
_WIKI_NDX_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
_WIKI_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DeepAlpha-Bot/1.0)"}

# 兜底成分股列表：当 FMP nasdaq_constituent 接口不可用时使用
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
    ("WBD",   "Warner Bros. Discovery",  "Communication Services"),
    ("ZS",    "Zscaler Inc.",            "Technology"),
    ("ALGN",  "Align Technology Inc.",   "Healthcare"),
    ("ENPH",  "Enphase Energy Inc.",     "Technology"),
    ("ILMN",  "Illumina Inc.",           "Healthcare"),
    ("GEHC",  "GE HealthCare Tech.",     "Healthcare"),
    ("ON",    "ON Semiconductor Corp.",  "Technology"),
    ("LULU",  "Lululemon Athletica",     "Consumer Cyclical"),
    ("SBUX",  "Starbucks Corp.",         "Consumer Cyclical"),
    ("CMCSA", "Comcast Corp.",           "Communication Services"),
    ("HON",   "Honeywell International", "Industrials"),
    ("EA",    "Electronic Arts Inc.",    "Communication Services"),
    ("EBAY",  "eBay Inc.",               "Consumer Cyclical"),
    ("DOCU",  "DocuSign Inc.",           "Technology"),
    ("XEL",   "Xcel Energy Inc.",        "Utilities"),
    ("ANSS",  "Ansys Inc.",              "Technology"),
    ("OKTA",  "Okta Inc.",               "Technology"),
    ("DDOG",  "Datadog Inc.",            "Technology"),
    ("INTC",  "Intel Corp.",             "Technology"),
    ("WDC",   "Western Digital Corp.",   "Technology"),
    ("STX",   "Seagate Technology",      "Technology"),
    ("SNDK",  "SanDisk Corp.",           "Technology"),
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


async def _fetch_constituents_from_wiki(client: httpx.AsyncClient) -> list[dict]:
    """从 Wikipedia 动态拉取纳斯达克 100 成分股."""
    try:
        resp = await client.get(_WIKI_NDX_URL, headers=_WIKI_HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.warning("wiki_ndx100_http_error", status=resp.status_code)
            return []
        constituents = await asyncio.get_event_loop().run_in_executor(
            None, _parse_wiki_html, resp.text
        )
        if constituents:
            logger.info("wiki_ndx100_fetched", count=len(constituents))
        return constituents
    except Exception as e:
        logger.warning("wiki_ndx100_fetch_failed", error=str(e))
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


async def compute_price_target_history(symbol: str) -> PriceTargetHistoryResponse:
    """拉取个股近 5 年分析师目标价，按季度聚合均值."""
    cutoff = date.today() - timedelta(days=5 * 365)
    quarterly: dict[str, list[float]] = defaultdict(list)

    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(15):
            resp = await client.get(
                f"{_FMP_STABLE}/price-target",
                params={"symbol": symbol.upper(), "page": page, "apikey": settings.FMP_API_KEY},
            )
            if resp.status_code != 200:
                break
            records = resp.json()
            if not isinstance(records, list) or not records:
                break

            stop = False
            for rec in records:
                dt_str = rec.get("publishedDate", "")
                pt = rec.get("priceTarget")
                if not dt_str or pt is None:
                    continue
                try:
                    dt = datetime.fromisoformat(dt_str[:10]).date()
                except ValueError:
                    continue
                if dt < cutoff:
                    stop = True
                    break
                q_num = (dt.month - 1) // 3 + 1
                quarterly[f"{dt.year} Q{q_num}"].append(float(pt))

            if stop:
                break

    quarters: list[PriceTargetQuarter] = [
        PriceTargetQuarter(
            label=label,
            avg_target=round(sum(vals) / len(vals), 2),
            count=len(vals),
        )
        for label, vals in quarterly.items()
        if vals
    ]

    def _sort_key(q: PriceTargetQuarter) -> tuple[int, int]:
        year, qn = q.label.split(" Q")
        return int(year), int(qn)

    quarters.sort(key=_sort_key)

    return PriceTargetHistoryResponse(symbol=symbol.upper(), quarters=quarters)
