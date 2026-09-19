"""信号雷达成分股解析：优先 FMP ETF 持仓动态刷新，失败回退 curated 静态清单。

FMP 对美股 ETF（QQQ）持仓覆盖较好；A 股 / 港股 ETF 覆盖有限，取不到时静默回退到
universe.py 的静态清单（仍可用）。解析结果按市场缓存 24h，避免每次扫描重复拉取。
名称优先用静态清单里的中文名，缺失时回退 FMP 英文名。
"""
from __future__ import annotations

import json

import httpx
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.services.signal_radar.universe import MarketUniverse, get_universe
from app.utils.market import InvalidSymbolError, fmp_symbol, normalize

_CACHE_PREFIX = "signal_radar:constituents"
_CACHE_TTL = 3600 * 24  # 24h
_MAX_CONSTITUENTS = 40   # 单市场扫描上限，控制扫描时长
_MIN_VALID = 20          # 动态结果至少这么多只才采用，否则回退静态


def _zh_name_map(u: MarketUniverse) -> dict[str, str]:
    return {sym: name for sym, name in u.constituents}


async def _fetch_fmp_holdings(etf_symbol: str) -> list[tuple[str, str, float]]:
    """拉取某 ETF 的成分（raw_symbol, name, weight），失败返回空列表。"""
    if not settings.FMP_API_KEY:
        return []
    key = settings.FMP_API_KEY
    endpoints = [
        ("https://financialmodelingprep.com/stable/etf/holdings", {"symbol": etf_symbol, "apikey": key}),
        (f"https://financialmodelingprep.com/api/v3/etf-holder/{etf_symbol}", {"apikey": key}),
    ]
    async with httpx.AsyncClient(timeout=20) as client:
        for url, params in endpoints:
            try:
                resp = await client.get(url, params=params)
            except Exception as e:  # noqa: BLE001
                logger.warning("signal_radar_holdings_fetch_error", etf=etf_symbol, url=url, error=str(e))
                continue
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list) or not data:
                continue
            out: list[tuple[str, str, float]] = []
            for row in data:
                if not isinstance(row, dict):
                    continue
                sym = row.get("asset") or row.get("symbol") or ""
                name = row.get("name") or sym
                weight = row.get("weightPercentage") or row.get("weight") or 0.0
                try:
                    weight = float(weight)
                except (TypeError, ValueError):
                    weight = 0.0
                if sym:
                    out.append((str(sym), str(name), weight))
            if out:
                logger.info("signal_radar_holdings_fetched", etf=etf_symbol, count=len(out))
                return out
    return []


def _map_to_universe(
    raw: list[tuple[str, str, float]], zh_names: dict[str, str]
) -> list[tuple[str, str]]:
    """把 FMP 原始成分归一化成 (裸代码, 中文名优先) 并按权重降序取前 N，去重。"""
    ranked = sorted(raw, key=lambda r: r[2], reverse=True)
    seen: set[str] = set()
    resolved: list[tuple[str, str]] = []
    for sym, name, _weight in ranked:
        try:
            _market, clean = normalize(sym)
        except InvalidSymbolError:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        resolved.append((clean, zh_names.get(clean, name)))
        if len(resolved) >= _MAX_CONSTITUENTS:
            break
    return resolved


async def resolve_constituents(market: str, *, redis: Redis) -> list[tuple[str, str]]:
    """解析某市场的扫描成分股：缓存 → FMP 动态 → 静态兜底。"""
    universe = get_universe(market)
    if universe is None:
        return []

    cache_key = f"{_CACHE_PREFIX}:{market}"
    try:
        cached = await redis.get(cache_key)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_constituents_cache_read_error", market=market, error=str(e))
        cached = None
    if cached:
        try:
            pairs = json.loads(cached)
            return [(str(s), str(n)) for s, n in pairs]
        except Exception:  # noqa: BLE001
            pass

    # 动态拉取（A 股 / 港股 ETF 用 FMP 代码形态）
    etf = universe.etf_symbol if market == "us" else _safe_fmp_symbol(universe.etf_symbol)
    raw = await _fetch_fmp_holdings(etf) if etf else []
    resolved = _map_to_universe(raw, _zh_name_map(universe))

    if len(resolved) < _MIN_VALID:
        logger.info(
            "signal_radar_constituents_fallback_static",
            market=market, dynamic=len(resolved),
        )
        resolved = list(universe.constituents)
    else:
        try:
            await redis.set(cache_key, json.dumps(resolved, ensure_ascii=False), ex=_CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_constituents_cache_write_error", market=market, error=str(e))

    return resolved


def _safe_fmp_symbol(symbol: str) -> str:
    try:
        return fmp_symbol(symbol)
    except InvalidSymbolError:
        return ""
