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

    if not _FMP_KEY:
        raise ValueError("数据源未配置：缺少 FMP_API_KEY 环境变量，请联系管理员")

    def _sync():
        # FMP 的 EOD 端点仅提供日线；周线在本地聚合，因此始终拉日线
        resp = httpx.get(
            _FMP_URL,
            params={"symbol": symbol, "from": start, "to": end, "apikey": _FMP_KEY},
            timeout=30,
        )
        if resp.status_code == 401:
            raise ValueError("数据源认证失败：FMP_API_KEY 无效")
        if resp.status_code == 429:
            raise ValueError("数据源请求过于频繁，请稍后再试")
        resp.raise_for_status()
        raw = resp.json()
        # FMP 出错时返回 dict（如 {"Error Message": ...}）而非 list
        if isinstance(raw, dict):
            err = raw.get("Error Message") or raw.get("error")
            if err:
                raise ValueError(f"数据源返回错误：{err}")
            records = raw.get("historical", [])
        else:
            records = raw
        records = [r for r in records if r.get("date")]
        records.sort(key=lambda r: r["date"])
        return [
            {"time": r["date"], "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "volume": r.get("volume", 0)}
            for r in records
        ]

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        daily = await loop.run_in_executor(pool, _sync)

    if freq == "weekly":
        return _resample_weekly(daily)
    return daily


def _resample_weekly(daily: list[dict]) -> list[dict]:
    """将日线按 ISO 周聚合为周K线。

    周内：open=首个交易日开盘，close=末个交易日收盘，
    high=区间最高，low=区间最低，volume=求和；时间取周内最后一个交易日。
    """
    from datetime import date

    buckets: dict[tuple[int, int], list[dict]] = {}
    order: list[tuple[int, int]] = []
    for bar in daily:
        d = date.fromisoformat(bar["time"][:10])
        iso = d.isocalendar()
        key = (iso[0], iso[1])  # (ISO 年, ISO 周)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(bar)

    weekly: list[dict] = []
    for key in order:
        group = buckets[key]  # daily 已按日期升序，组内同样有序
        weekly.append({
            "time": group[-1]["time"],
            "open": group[0]["open"],
            "high": max(b["high"] for b in group),
            "low": min(b["low"] for b in group),
            "close": group[-1]["close"],
            "volume": sum(b.get("volume", 0) for b in group),
        })
    return weekly


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
