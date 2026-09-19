"""信号雷达成分股解析：按 universe 的来源策略动态拉取，失败回退 curated 静态清单。

来源策略（universe.source）：
- etf_holdings：FMP ETF 持仓（美股 QQQ 覆盖好；A 股/港股 ETF 覆盖有限，多回退静态）；
- fmp_sp500  ：FMP 标普500 成分端点（拿全量 ~500）；
- akshare_index：akshare 指数成分（沪深300 / 恒生指数全量），在线程里跑、失败回退静态。

结果按 (market, universe) 缓存 24h，避免每次扫描重复拉取。名称优先用静态清单里的
中文名，缺失时回退来源给的名称。任何来源拿不到足量（< _MIN_VALID）时回退静态清单，
保证任何情况下都有可扫的范围。
"""
from __future__ import annotations

import asyncio
import json

import httpx
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.services.signal_radar.universe import (
    SOURCE_AKSHARE_INDEX,
    SOURCE_FMP_SP500,
    MarketUniverse,
    get_universe,
)
from app.utils.market import InvalidSymbolError, fmp_symbol, normalize

_CACHE_PREFIX = "signal_radar:constituents"
_CACHE_TTL = 3600 * 24  # 24h
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


async def _fetch_fmp_sp500() -> list[tuple[str, str, float]]:
    """拉取标普500 全量成分（symbol, name, 0.0）。FMP 该端点不带权重，权重给 0 不排序。"""
    if not settings.FMP_API_KEY:
        return []
    key = settings.FMP_API_KEY
    endpoints = [
        ("https://financialmodelingprep.com/stable/sp500-constituent", {"apikey": key}),
        ("https://financialmodelingprep.com/api/v3/sp500_constituent", {"apikey": key}),
    ]
    async with httpx.AsyncClient(timeout=20) as client:
        for url, params in endpoints:
            try:
                resp = await client.get(url, params=params)
            except Exception as e:  # noqa: BLE001
                logger.warning("signal_radar_sp500_fetch_error", url=url, error=str(e))
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
                sym = row.get("symbol") or ""
                name = row.get("name") or sym
                if sym:
                    out.append((str(sym), str(name), 0.0))
            if out:
                logger.info("signal_radar_sp500_fetched", count=len(out))
                return out
    return []


def _akshare_index_cons_blocking(index_arg: str) -> list[tuple[str, str, float]]:
    """在工作线程里用 akshare 拉指数成分（同步库，务必用 to_thread 调用）。

    akshare 未安装或接口变动时抛异常，由调用方兜底回退静态清单。沪深300 用中证
    指数成分端点；恒生指数（HSI）akshare 覆盖不稳定，取不到就返回空、回退静态。
    """
    import akshare as ak  # 延迟导入：未安装时由外层 try/except 兜底

    rows: list[tuple[str, str, float]] = []
    if index_arg == "HSI":
        # 港股指数成分 akshare 覆盖不稳定，交由静态清单兜底。
        fn = getattr(ak, "index_stock_cons_sina", None)
        if fn is None:
            return []
        df = fn(symbol="HSI")
        for _, r in df.iterrows():
            sym = str(r.get("代码") or r.get("symbol") or "").strip()
            name = str(r.get("名称") or r.get("name") or sym).strip()
            if sym:
                rows.append((sym, name, 0.0))
        return rows

    # A 股指数（沪深300=000300）：优先中证官方成分端点，回退通用端点。
    for fn_name in ("index_stock_cons_csindex", "index_stock_cons"):
        fn = getattr(ak, fn_name, None)
        if fn is None:
            continue
        try:
            df = fn(symbol=index_arg)
        except Exception:  # noqa: BLE001 换下一个端点
            continue
        for _, r in df.iterrows():
            sym = str(r.get("成分券代码") or r.get("品种代码") or r.get("代码") or "").strip()
            name = str(r.get("成分券名称") or r.get("品种名称") or r.get("名称") or sym).strip()
            if sym:
                rows.append((sym, name, 0.0))
        if rows:
            return rows
    return rows


async def _fetch_akshare_index(index_arg: str) -> list[tuple[str, str, float]]:
    """异步包装：akshare 指数成分拉取，任何异常（含未安装）都吞掉返回空。"""
    try:
        rows = await asyncio.to_thread(_akshare_index_cons_blocking, index_arg)
        if rows:
            logger.info("signal_radar_akshare_index_fetched", index=index_arg, count=len(rows))
        return rows
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_akshare_index_error", index=index_arg, error=str(e))
        return []


def _map_to_universe(
    raw: list[tuple[str, str, float]], zh_names: dict[str, str], *, max_scan: int
) -> list[tuple[str, str]]:
    """把原始成分归一化成 (裸代码, 中文名优先) 并按权重降序取前 max_scan，去重。

    权重全为 0（如 sp500/akshare 端点不带权重）时保持来源原始顺序。
    """
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
        if len(resolved) >= max_scan:
            break
    return resolved


async def _fetch_dynamic(universe: MarketUniverse) -> list[tuple[str, str, float]]:
    """按 universe 的来源策略动态拉取原始成分。"""
    if universe.source == SOURCE_FMP_SP500:
        return await _fetch_fmp_sp500()
    if universe.source == SOURCE_AKSHARE_INDEX:
        return await _fetch_akshare_index(universe.source_arg)
    # etf_holdings：A 股/港股 ETF 用 FMP 代码形态
    etf = universe.etf_symbol if universe.market == "us" else _safe_fmp_symbol(universe.etf_symbol)
    return await _fetch_fmp_holdings(etf) if etf else []


async def resolve_constituents(
    market: str, *, redis: Redis, universe_key: str | None = None,
) -> list[tuple[str, str]]:
    """解析某 (市场, universe) 的扫描成分股：缓存 → 动态来源 → 静态兜底。"""
    universe = get_universe(market, universe_key)
    if universe is None:
        return []

    cache_key = f"{_CACHE_PREFIX}:{universe.market}:{universe.key}"
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

    raw = await _fetch_dynamic(universe)
    resolved = _map_to_universe(raw, _zh_name_map(universe), max_scan=universe.max_scan)

    if len(resolved) < _MIN_VALID:
        logger.info(
            "signal_radar_constituents_fallback_static",
            market=market, universe=universe.key, dynamic=len(resolved),
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
