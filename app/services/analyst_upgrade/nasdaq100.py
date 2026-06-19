"""纳斯达克 100 分析师目标价上调筛选服务."""

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx

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


async def _fetch_constituents(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        f"{_FMP_V3}/nasdaq_constituent",
        params={"apikey": settings.FMP_API_KEY},
    )
    if resp.status_code != 200:
        logger.warning("nasdaq_constituent_error", status=resp.status_code)
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


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
        if not constituents:
            return Nasdaq100UpgradesResponse(
                as_of=date.today().isoformat(),
                total_constituents=0,
                upgrade_count=0,
                stocks=[],
            )

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
