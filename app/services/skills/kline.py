"""K 线拉取 + Redis 缓存（user_id 隔离 key）"""
from __future__ import annotations

import os
import re

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger

_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_FMP_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"
_CACHE_TTL = 3600 * 24  # 24h


def _cache_key(user_id: int | None, symbol: str, start: str, end: str, freq: str) -> str:
    prefix = f"u{user_id}" if user_id else "public"
    return f"skill_kline:{prefix}:{symbol}:{start}:{end}:{freq}"


def _is_a_share(symbol: str) -> bool:
    clean = re.sub(r"^(SH|SZ|sh|sz)", "", symbol).strip()
    return bool(re.match(r"^\d{6}$", clean))


async def fetch_kline(
    user_id: int | None,
    symbol: str,
    start_date: str,
    end_date: str,
    freq: str = "daily",
    *,
    redis: Redis | None = None,
) -> list[dict]:
    """获取 K 线数据（Redis 优先），返回 list[{time, open, high, low, close, volume}]。"""
    cache_key = _cache_key(user_id, symbol, start_date, end_date, freq)

    if redis:
        cached = await get_json(redis, cache_key)
        if cached:
            logger.debug("kline_cache_hit", key=cache_key)
            return cached

    logger.info("kline_fetch_start", symbol=symbol, start=start_date, end=end_date)

    # A 股用 akshare，美股用 FMP
    if _is_a_share(symbol):
        bars = await _fetch_a_share(symbol, start_date, end_date, freq)
    else:
        bars = await _fetch_fmp(symbol, start_date, end_date, freq)

    if redis and bars:
        await set_json(redis, cache_key, bars, expire=_CACHE_TTL)

    return bars


async def _fetch_fmp(symbol: str, start: str, end: str, freq: str) -> list[dict]:
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _sync():
        resp = httpx.get(
            _FMP_URL,
            params={"symbol": symbol, "from": start, "to": end,
                    "apikey": _FMP_KEY, "period": freq},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        records = raw if isinstance(raw, list) else raw.get("historical", [])
        records.sort(key=lambda r: r["date"])
        return [
            {"time": r["date"], "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "volume": r.get("volume", 0)}
            for r in records
        ]

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, _sync)


async def _fetch_a_share(symbol: str, start: str, end: str, freq: str) -> list[dict]:
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _sync():
        import akshare as ak  # noqa: PLC0415
        clean = re.sub(r"^(SH|SZ|sh|sz)", "", symbol).strip()
        period = "daily" if freq == "daily" else "weekly"
        df = ak.stock_zh_a_hist(
            symbol=clean, period=period,
            start_date=start.replace("-", ""), end_date=end.replace("-", ""),
            adjust="qfq",
        )
        df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                 "最高": "high", "最低": "low", "成交量": "volume"})
        df["date"] = df["date"].astype(str)
        return [
            {"time": row["date"], "open": float(row["open"]), "high": float(row["high"]),
             "low": float(row["low"]), "close": float(row["close"]),
             "volume": float(row.get("volume", 0))}
            for _, row in df.iterrows()
        ]

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, _sync)


def bars_to_price_records(bars: list[dict]) -> list[dict]:
    """将 bars 格式转为 sandbox 执行时用的 price_records 格式。"""
    return [
        {"date": b["time"], "open": b["open"], "high": b["high"],
         "low": b["low"], "close": b["close"], "volume": b["volume"]}
        for b in bars
    ]
