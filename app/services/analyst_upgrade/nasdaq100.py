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
    StockPricePoint,
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
# 完整的 101 只当前纳斯达克 100 成分（含 GOOGL/GOOG 双类股）
# 数据来源：2026-05 Wikipedia Nasdaq-100 成分表，经两个独立数据源交叉校验一致
# 格式：(symbol, name, sector)
_FALLBACK_NDX100: list[tuple[str, str, str]] = [
    # 信息技术
    ("AAPL", "Apple Inc.",                    "Technology"),
    ("ADBE", "Adobe Inc.",                    "Technology"),
    ("ADI",  "Analog Devices",                "Technology"),
    ("ADSK", "Autodesk",                      "Technology"),
    ("AMAT", "Applied Materials",             "Technology"),
    ("AMD",  "Advanced Micro Devices",        "Technology"),
    ("APP",  "AppLovin",                      "Technology"),
    ("ARM",  "Arm Holdings",                  "Technology"),
    ("ASML", "ASML Holding",                  "Technology"),
    ("AVGO", "Broadcom",                      "Technology"),
    ("CDNS", "Cadence Design Systems",        "Technology"),
    ("CRWD", "CrowdStrike",                   "Technology"),
    ("CTSH", "Cognizant",                     "Technology"),
    ("DASH", "DoorDash",                      "Technology"),
    ("DDOG", "Datadog",                       "Technology"),
    ("FTNT", "Fortinet",                      "Technology"),
    ("GOOG", "Alphabet Inc. (Class C)",       "Technology"),
    ("GOOGL","Alphabet Inc. (Class A)",       "Technology"),
    ("INTC", "Intel",                         "Technology"),
    ("INTU", "Intuit",                        "Technology"),
    ("KLAC", "KLA Corporation",               "Technology"),
    ("LITE", "Lumentum",                      "Technology"),
    ("LRCX", "Lam Research",                  "Technology"),
    ("MCHP", "Microchip Technology",          "Technology"),
    ("META", "Meta Platforms",                "Technology"),
    ("MPWR", "Monolithic Power Systems",      "Technology"),
    ("MRVL", "Marvell Technology",            "Technology"),
    ("MSFT", "Microsoft",                     "Technology"),
    ("MSTR", "MicroStrategy",                 "Technology"),
    ("MU",   "Micron Technology",             "Technology"),
    ("NVDA", "Nvidia",                        "Technology"),
    ("NXPI", "NXP Semiconductors",            "Technology"),
    ("PANW", "Palo Alto Networks",            "Technology"),
    ("PDD",  "PDD Holdings",                  "Technology"),
    ("PLTR", "Palantir Technologies",         "Technology"),
    ("QCOM", "Qualcomm",                      "Technology"),
    ("ROP",  "Roper Technologies",            "Technology"),
    ("SHOP", "Shopify",                       "Technology"),
    ("SNDK", "Sandisk",                       "Technology"),
    ("SNPS", "Synopsys",                      "Technology"),
    ("STX",  "Seagate Technology",            "Technology"),
    ("TRI",  "Thomson Reuters",               "Technology"),
    ("TXN",  "Texas Instruments",             "Technology"),
    ("WDAY", "Workday, Inc.",                 "Technology"),
    ("WDC",  "Western Digital",               "Technology"),
    ("ZS",   "Zscaler",                       "Technology"),
    # 通信服务
    ("CHTR", "Charter Communications",        "Communication Services"),
    ("CMCSA","Comcast",                       "Communication Services"),
    ("CSCO", "Cisco",                         "Communication Services"),
    ("TMUS", "T-Mobile US",                   "Communication Services"),
    # 可选消费
    ("ABNB", "Airbnb",                        "Consumer Discretionary"),
    ("AMZN", "Amazon",                        "Consumer Discretionary"),
    ("BKNG", "Booking Holdings",              "Consumer Discretionary"),
    ("COST", "Costco",                        "Consumer Discretionary"),
    ("CPRT", "Copart",                        "Consumer Discretionary"),
    ("EA",   "Electronic Arts",               "Consumer Discretionary"),
    ("MAR",  "Marriott International",        "Consumer Discretionary"),
    ("MELI", "Mercado Libre",                 "Consumer Discretionary"),
    ("NFLX", "Netflix, Inc.",                 "Consumer Discretionary"),
    ("ORLY", "O'Reilly Automotive",           "Consumer Discretionary"),
    ("PCAR", "Paccar",                        "Consumer Discretionary"),
    ("ROST", "Ross Stores",                   "Consumer Discretionary"),
    ("SBUX", "Starbucks",                     "Consumer Discretionary"),
    ("TSLA", "Tesla, Inc.",                   "Consumer Discretionary"),
    ("TTWO", "Take-Two Interactive",          "Consumer Discretionary"),
    ("WBD",  "Warner Bros. Discovery",        "Consumer Discretionary"),
    ("WMT",  "Walmart",                       "Consumer Discretionary"),
    # 必需消费
    ("CCEP", "Coca-Cola Europacific Partners","Consumer Staples"),
    ("KDP",  "Keurig Dr Pepper",              "Consumer Staples"),
    ("KHC",  "Kraft Heinz",                   "Consumer Staples"),
    ("MDLZ", "Mondelez International",        "Consumer Staples"),
    ("MNST", "Monster Beverage",              "Consumer Staples"),
    ("PEP",  "PepsiCo",                       "Consumer Staples"),
    # 医疗健康
    ("ALNY", "Alnylam Pharmaceuticals",       "Health Care"),
    ("AMGN", "Amgen",                         "Health Care"),
    ("DXCM", "DexCom",                        "Health Care"),
    ("GEHC", "GE HealthCare",                 "Health Care"),
    ("GILD", "Gilead Sciences",               "Health Care"),
    ("IDXX", "Idexx Laboratories",            "Health Care"),
    ("INSM", "Insmed Incorporated",           "Health Care"),
    ("ISRG", "Intuitive Surgical",            "Health Care"),
    ("REGN", "Regeneron Pharmaceuticals",     "Health Care"),
    ("VRTX", "Vertex Pharmaceuticals",        "Health Care"),
    # 工业
    ("ADP",  "Automatic Data Processing",     "Industrials"),
    ("AXON", "Axon Enterprise",               "Industrials"),
    ("CSX",  "CSX Corporation",               "Industrials"),
    ("CTAS", "Cintas",                        "Industrials"),
    ("FAST", "Fastenal",                      "Industrials"),
    ("FER",  "Ferrovial",                     "Industrials"),
    ("HON",  "Honeywell",                     "Industrials"),
    ("ODFL", "Old Dominion Freight Line",     "Industrials"),
    ("PAYX", "Paychex",                       "Industrials"),
    ("PYPL", "PayPal",                        "Industrials"),
    ("VRSK", "Verisk Analytics",              "Industrials"),
    # 公用事业
    ("AEP",  "American Electric Power",       "Utilities"),
    ("CEG",  "Constellation Energy",          "Utilities"),
    ("EXC",  "Exelon",                        "Utilities"),
    ("XEL",  "Xcel Energy",                   "Utilities"),
    # 能源
    ("BKR",  "Baker Hughes",                  "Energy"),
    ("FANG", "Diamondback Energy",            "Energy"),
    # 材料
    ("LIN",  "Linde plc",                     "Materials"),
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
        name_col = next((c for c in cols if "company" in c.lower() or "name" in c.lower() or "security" in c.lower()), None)
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

    # 并发拉取合格股票近 5 年月度目标价，嵌入 recent_points 供 sparkline 使用（与 modal 数据范围一致）
    if stocks:
        cutoff_5y = date.today() - timedelta(days=5 * 365)
        sem2 = asyncio.Semaphore(10)
        async with httpx.AsyncClient(timeout=30) as client2:
            history_pairs = await asyncio.gather(
                *[_compute_recent_points(client2, s.symbol, sem2, cutoff_5y) for s in stocks]
            )
        history_map = dict(history_pairs)
        for stock in stocks:
            stock.recent_points = history_map.get(stock.symbol, [])

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


# 逐条目标价端点候选：命中即返回，否则依次降级。
# 首选 TipRanks point-in-time（与富途同源，覆盖全、更新快，尤其对次新股无明显滞后），
# 需 FMP TipRanks add-on；未订阅时返回非列表结果，自动降级到 price-target-news（TheFly 源）。
_FMP_PT_URLS = (
    f"{_FMP_STABLE}/tipranks-pit-by-symbol",
    f"{_FMP_STABLE}/price-target-news",
    "https://financialmodelingprep.com/api/v4/price-target",
    f"{_FMP_STABLE}/price-target",
)
# 不同端点/版本的字段名差异，做兼容（TipRanks 用 ratingDate/ratedOn）
_PT_DATE_FIELDS = (
    "publishedDate",
    "ratingDate",
    "ratedOn",
    "date",
    "published_date",
    "datePublished",
    "publishedAt",
)
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
    """逐条拉取个股分析师目标价记录，依次尝试多个端点，命中即返回.

    遇到 429 限速时使用指数退避重试（5s → 10s → 20s），确保多页数据能完整拉取，
    避免分析师覆盖多（报告数 > 100）的股票因第 2 页限速而数据被截断。
    """
    for url in _FMP_PT_URLS:
        records: list[dict] = []
        for page in range(20):
            resp = None
            for wait_secs in (0, 5, 10, 20):  # 最多重试 3 次，指数退避
                if wait_secs:
                    await asyncio.sleep(wait_secs)
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
                    resp = None
                    break
                if resp.status_code != 429:
                    break  # 非 429 则退出重试循环

            if resp is None or resp.status_code != 200:
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


async def _compute_recent_points(
    client: httpx.AsyncClient,
    sym: str,
    sem: asyncio.Semaphore,
    cutoff: date,
) -> tuple[str, list[PriceTargetPoint]]:
    """拉取单只股票近期月度目标价（用于列表 sparkline）."""
    async with sem:
        records = await _fetch_price_target_records(client, sym)
    monthly: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        dt = _extract_pt_date(rec)
        pt = _extract_pt_value(rec)
        if dt is None or pt is None or dt < cutoff:
            continue
        monthly[f"{dt.year}-{dt.month:02d}"].append(pt)
    pts = sorted(
        [
            PriceTargetPoint(
                label=lbl,
                avg_target=round(sum(v) / len(v), 2),
                count=len(v),
            )
            for lbl, v in monthly.items()
            if v
        ],
        key=lambda p: p.label,
    )
    return sym, pts


def _aggregate_monthly_points(records: list[dict], start: date, end: date) -> list[PriceTargetPoint]:
    """将逐条目标价记录按月聚合为平均目标价点，仅保留 [start, end] 区间内的记录."""
    monthly: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        dt = _extract_pt_date(rec)
        pt = _extract_pt_value(rec)
        if dt is None or pt is None or dt < start or dt > end:
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
    return points


async def compute_price_target_history(symbol: str) -> PriceTargetHistoryResponse:
    """拉取个股近 5 年分析师目标价，按月聚合均值."""
    start = date.today() - timedelta(days=5 * 365)
    end = date.today()

    async with httpx.AsyncClient(timeout=30) as client:
        records = await _fetch_price_target_records(client, symbol)

    points = _aggregate_monthly_points(records, start, end)

    logger.info("price_target_history_computed", symbol=symbol, months=len(points))

    return PriceTargetHistoryResponse(symbol=symbol.upper(), points=points)


async def _fetch_monthly_prices(
    client: httpx.AsyncClient, symbol: str, start: date, end: date
) -> list[StockPricePoint]:
    """拉取个股日线收盘价，按月聚合为月末收盘价（每月最后一个交易日）."""
    try:
        resp = await client.get(
            f"{_FMP_STABLE}/historical-price-eod/full",
            params={
                "symbol": symbol.upper(),
                "from": start.isoformat(),
                "to": end.isoformat(),
                "apikey": settings.FMP_API_KEY,
            },
        )
    except Exception as e:
        logger.warning("stock_price_fetch_error", symbol=symbol, error=str(e))
        return []

    if resp.status_code != 200:
        logger.warning("stock_price_http_error", symbol=symbol, status=resp.status_code)
        return []

    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return []

    # 每月保留日期最大的一条（月末收盘）
    monthly: dict[str, tuple[date, float]] = {}
    for r in rows:
        raw_date = r.get("date")
        close = r.get("close")
        if raw_date is None or close is None:
            continue
        try:
            dt = datetime.fromisoformat(str(raw_date)[:10]).date()
            close_val = float(close)
        except (TypeError, ValueError):
            continue
        if dt < start or dt > end:
            continue
        key = f"{dt.year}-{dt.month:02d}"
        if key not in monthly or dt > monthly[key][0]:
            monthly[key] = (dt, close_val)

    return [
        StockPricePoint(label=label, close=round(price, 2))
        for label, (_, price) in sorted(monthly.items(), key=lambda kv: kv[0])
    ]


async def compute_custom_price_target_history(
    symbol: str, start: date, end: date
) -> PriceTargetHistoryResponse:
    """拉取个股指定时间区间内分析师目标价（按月聚合均值）与月度股价（用于自定义查询）."""
    async with httpx.AsyncClient(timeout=30) as client:
        records, price_points = await asyncio.gather(
            _fetch_price_target_records(client, symbol),
            _fetch_monthly_prices(client, symbol, start, end),
        )

    points = _aggregate_monthly_points(records, start, end)

    logger.info(
        "custom_price_target_history_computed",
        symbol=symbol,
        start=start.isoformat(),
        end=end.isoformat(),
        months=len(points),
        price_months=len(price_points),
    )

    return PriceTargetHistoryResponse(
        symbol=symbol.upper(), points=points, price_points=price_points
    )
