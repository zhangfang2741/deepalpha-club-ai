"""机构资金信号数据抓取（FMP stable API）。

单源失败返回空/None，不抛异常——由 calculator 决定降级为 partial。
"""
import httpx

from app.core.config import settings
from app.core.logging import logger

_FMP_STABLE = "https://financialmodelingprep.com/stable"
_TIMEOUT = 15


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> list | dict | None:
    try:
        resp = await client.get(
            f"{_FMP_STABLE}/{path}",
            params={**params, "apikey": settings.FMP_API_KEY},
        )
        if resp.status_code != 200:
            logger.warning("institutional_signals_fetch_non200", path=path, status=resp.status_code)
            return None
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            return None
        return data
    except Exception as e:
        logger.warning("institutional_signals_fetch_error", path=path, error=str(e))
        return None


async def fetch_profile(client: httpx.AsyncClient, symbol: str) -> dict | None:
    """公司档案（取公司名）。"""
    data = await _get(client, "profile", {"symbol": symbol})
    if isinstance(data, list) and data:
        return data[0]
    return None


async def fetch_price_target_summary(client: httpx.AsyncClient, symbol: str) -> dict | None:
    """目标价汇总（近月/季/年均值 + 家数）。"""
    data = await _get(client, "price-target-summary", {"symbol": symbol})
    if isinstance(data, list) and data:
        return data[0]
    return None


async def fetch_grades_historical(client: httpx.AsyncClient, symbol: str) -> list[dict]:
    """评级历史（各月强买/买/持有/卖出家数）。"""
    data = await _get(client, "grades-historical", {"symbol": symbol, "limit": 12})
    return data if isinstance(data, list) else []


async def fetch_price_history(client: httpx.AsyncClient, symbol: str, from_: str, to: str) -> list[dict]:
    """日线 EOD，按日期升序，标准化字段。"""
    data = await _get(client, "historical-price-eod/full",
                      {"symbol": symbol, "from": from_, "to": to})
    if not isinstance(data, list):
        return []
    rows = [
        {"date": r["date"], "open": r.get("open", 0), "high": r.get("high", 0),
         "low": r.get("low", 0), "close": r.get("close", 0), "volume": r.get("volume", 0)}
        for r in data if r.get("date")
    ]
    return sorted(rows, key=lambda x: x["date"])
