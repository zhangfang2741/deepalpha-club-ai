"""K 线拉取 + Redis 缓存（user_id 隔离 key）"""
from __future__ import annotations

import os

import httpx
from redis.asyncio import Redis
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.utils.market import (
    Market,
    eastmoney_secid,
    fmp_symbol,
    normalize as normalize_symbol,
)

class _PremiumRequiredError(Exception):
    """FMP 返回 402：该标的不在当前套餐内。"""


_EASTMONEY_URL = "https://33.push2his.eastmoney.com/api/qt/stock/kline/get"


_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_FMP_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"
_CACHE_TTL = 3600 * 24  # 24h


class _RateLimitError(Exception):
    """FMP 返回 429 时抛出的可重试异常（内部使用，不透传给用户）。"""


def _cache_key(user_id: int | None, symbol: str, start: str, end: str, freq: str) -> str:
    prefix = f"u{user_id}" if user_id else "public"
    return f"skill_kline:{prefix}:{symbol}:{start}:{end}:{freq}"


# 市场判别已提升到 app/utils/market.py：这里原本只区分「6 位数字 = A 股，
# 其余 = 美股」，加了港股之后三个市场的规则放在一处才好维护。


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
    # 先归一化再算缓存键：否则 0700 / 00700 / 0700.HK 是同一支股票却各存一份
    market, clean_symbol = normalize_symbol(symbol)
    cache_key = _cache_key(user_id, clean_symbol, start_date, end_date, freq)

    if redis:
        cached = await get_json(redis, cache_key)
        if cached:
            logger.debug("kline_cache_hit", key=cache_key)
            return cached

    logger.info("kline_fetch_start", symbol=symbol, start=start_date, end=end_date)

    # 美股走 FMP，A 股与港股走东方财富。
    #
    # 为什么不统一用 FMP：实测当前 key 的套餐只含美股，A 股 600519.SS 和
    # 港股 0700.HK 的历史行情端点都返回 402（"not available under your current
    # subscription"）。代码格式没错——search-symbol 能查到这两个标的。
    #
    # 为什么不用 akshare：它的港股接口请求同一个东方财富后端时会被断连，
    # 而自己直接请求是通的。少一层猜不透的封装，也少一个重依赖。
    if market is Market.US:
        bars = await _fetch_fmp(fmp_symbol(symbol), start_date, end_date, freq)
    else:
        bars = await _fetch_eastmoney(eastmoney_secid(symbol), start_date, end_date, freq)

    if redis and bars:
        await set_json(redis, cache_key, bars, expire=_CACHE_TTL)

    return bars


async def _fetch_fmp(symbol: str, start: str, end: str, freq: str) -> list[dict]:
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    if not _FMP_KEY:
        raise ValueError("数据源未配置：缺少 FMP_API_KEY 环境变量，请联系管理员")

    # 429 / 网络抖动时指数退避重试（2s、4s、最多 8s），避免偶发限流直接失败
    @retry(
        retry=retry_if_exception_type((_RateLimitError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    def _sync():
        # FMP 的 EOD 端点仅提供日线；周线在本地聚合，因此始终拉日线
        resp = httpx.get(
            _FMP_URL,
            params={"symbol": symbol, "from": start, "to": end, "apikey": _FMP_KEY},
            timeout=30,
        )
        if resp.status_code == 401:
            raise ValueError("数据源认证失败：FMP_API_KEY 无效")
        if resp.status_code == 402:
            # 非美股标的在免费/低档套餐下会走到这里，交给上层决定兜底还是报错
            raise _PremiumRequiredError
        if resp.status_code == 429:
            # 交给 tenacity 重试；用尽后在下方转换为可读错误
            raise _RateLimitError
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
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            daily = await loop.run_in_executor(pool, _sync)
    except _RateLimitError:
        # 多次重试仍被限流，透传可读信息给用户
        raise ValueError("数据源请求过于频繁，请稍后再试")

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


async def _fetch_eastmoney(secid: str, start: str, end: str, freq: str) -> list[dict]:
    """A 股与港股 K 线，直连东方财富行情接口。

    两个市场共用一个接口，只有 secid 的市场前缀不同（1=沪 0=深 116=港），
    所以不必像原来那样为 A 股和港股各写一份。

    数据源与 akshare 的港股/A 股接口相同，区别只是少了一层封装。
    """
    # klt: 101=日线 102=周线；fqt: 1=前复权，与原 akshare 链路的 adjust="qfq" 一致
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        # 依次为：日期、开盘、收盘、最高、最低、成交量、成交额
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": "101" if freq == "daily" else "102",
        "fqt": "1",
        "beg": start.replace("-", ""),
        "end": end.replace("-", ""),
    }

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=6),
        reraise=True,
    )
    def _sync() -> list[dict]:
        # trust_env=False：.env 里的 HTTP_PROXY/HTTPS_PROXY 是给境外 LLM API 用的，
        # 拿它去访问东方财富只会被代理断连（本地实测 RemoteProtocolError）。
        # 这个接口不需要代理，直连即可。
        resp = httpx.get(_EASTMONEY_URL, params=params, timeout=30, trust_env=False)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data")
        if not data or not data.get("klines"):
            raise ValueError("未获取到该标的的 K 线数据，请检查代码与日期范围")

        bars: list[dict] = []
        for line in data["klines"]:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            bars.append({
                "time": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
            })
        return bars

    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return await loop.run_in_executor(pool, _sync)
        except (httpx.RemoteProtocolError, httpx.TransportError) as exc:
            # 东方财富对高频请求会直接断连并封一段时间的 IP（实测十几次连续
            # 请求即触发）。裸异常抛给用户没有任何信息量，转成能看懂的话。
            logger.warning("eastmoney_unavailable", secid=secid, error=str(exc))
            raise ValueError(
                "行情数据源暂时不可用（可能被限流），请稍后重试"
            ) from exc


def bars_to_price_records(bars: list[dict]) -> list[dict]:
    """将 bars 格式转为 sandbox 执行时用的 price_records 格式。"""
    return [
        {"date": b["time"], "open": b["open"], "high": b["high"],
         "low": b["low"], "close": b["close"], "volume": b["volume"]}
        for b in bars
    ]
