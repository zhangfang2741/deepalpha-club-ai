"""信号雷达成分股解析：按 universe 的来源策略动态拉取，失败回退 curated 静态清单。

来源策略（universe.source）：
- etf_holdings：FMP ETF 持仓（美股 QQQ 覆盖好；A 股/港股 ETF 覆盖有限，多回退静态）；
- fmp_sp500  ：FMP 标普500 成分端点（拿全量 ~500）；
- akshare_index：akshare 指数成分（沪深300 / 科创50 / 恒生指数全量），在线程里跑、失败回退静态；
- nasdaq100_list：纳斯达克官方成分列表（纳指100 全量）；
- wiki_sp500   ：维基百科标普500 成分表（全量 ~503）。
FMP 当前套餐不含 ETF 持仓与指数成分端点（402），美股全量改走后两者。

结果按 (market, universe) 缓存 24h，避免每次扫描重复拉取。名称优先用静态清单里的
中文名，美股再查东方财富的中文名（见 _resolve_us_names，覆盖面远超 curated 清单），
最后回退来源给的名称。任何来源拿不到足量（< _MIN_VALID）时回退静态清单，保证任何
情况下都有可扫的范围。
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.services.signal_radar.universe import (
    SOURCE_AKSHARE_INDEX,
    SOURCE_FMP_SP500,
    SOURCE_NASDAQ100,
    SOURCE_WIKI_SP500,
    MarketUniverse,
    get_universe,
    resolve_name,
)
from app.utils.market import InvalidSymbolError, fmp_symbol, normalize

# v2：美股无中文名改为留空，旧缓存里的英文全称需要失效
# v3：美股中文名接入东方财富后，旧缓存里大量空名称需要一次性失效重建
_CACHE_PREFIX = "signal_radar:constituents:v3"
_CACHE_TTL = 3600 * 24  # 24h
_MIN_VALID = 20          # 动态结果至少这么多只才采用，否则回退静态

# 美股中文名：东方财富美股搜索接口（公开、免鉴权，token 为其前端固定值非密钥）覆盖面
# 远超本文件 curated 清单（几千只美股，含标普500/纳指100 全量的绝大多数）。按代码缓存
# 30 天——公司中文译名基本不变，减少下次成分刷新时的请求量。
_EASTMONEY_SUGGEST_URL = "https://searchapi.eastmoney.com/api/suggest/get"
_EASTMONEY_SUGGEST_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"
_US_NAME_CACHE_PREFIX = "signal_radar:us_name:v1"
_US_NAME_CACHE_TTL = 3600 * 24 * 30  # 30 天
_US_NAME_CONCURRENCY = 8


def _zh_name_map(u: MarketUniverse) -> dict[str, str]:
    return {sym: name for sym, name in u.constituents}


def parse_eastmoney_us_suggest(payload: object, symbol: str) -> str | None:
    """从东方财富搜索接口的返回里挑出某代码的中文名。

    搜索是模糊匹配，同代码可能还挂着债券/优先股条目（如 ORCL_D）；只认代码精确
    相同、且是普通股（TypeUS=1）的美股条目，查不到 / payload 形状不对都返回 None。
    """
    try:
        rows = payload["QuotationCodeTable"]["Data"]  # type: ignore[index]
    except (TypeError, KeyError):
        return None
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if (str(r.get("Code", "")).upper() == symbol.upper()
                and r.get("Classify") == "UsStock" and r.get("TypeUS") == "1"):
            name = str(r.get("Name") or "").strip()
            return name or None
    return None


async def _fetch_eastmoney_us_name(client: httpx.AsyncClient, symbol: str) -> str | None:
    """查东方财富美股搜索接口的中文名；查不到 / 接口异常都返回 None，不影响其他标的。"""
    try:
        resp = await client.get(_EASTMONEY_SUGGEST_URL, params={
            "input": symbol, "type": "14", "token": _EASTMONEY_SUGGEST_TOKEN, "count": 5,
        })
        if resp.status_code != 200:
            return None
        return parse_eastmoney_us_suggest(resp.json(), symbol)
    except Exception:  # noqa: BLE001 单只查询失败不影响其他标的
        return None


async def _resolve_us_names(symbols: list[str], *, redis: Redis | None) -> dict[str, str]:
    """批量取一组美股代码的中文名（东方财富，命中 Redis 缓存的直接用，其余并发查询）。"""
    result: dict[str, str] = {}
    to_fetch: list[str] = []
    for sym in symbols:
        cached = None
        if redis is not None:
            try:
                cached = await redis.get(f"{_US_NAME_CACHE_PREFIX}:{sym}")
            except Exception as e:  # noqa: BLE001
                logger.warning("signal_radar_us_name_cache_read_error", symbol=sym, error=str(e))
        if cached:
            result[sym] = cached if isinstance(cached, str) else cached.decode()
        else:
            to_fetch.append(sym)

    if not to_fetch:
        return result

    sem = asyncio.Semaphore(_US_NAME_CONCURRENCY)

    async def _one(client: httpx.AsyncClient, sym: str) -> None:
        async with sem:
            name = await _fetch_eastmoney_us_name(client, sym)
        if not name:
            return
        result[sym] = name
        if redis is not None:
            try:
                await redis.set(f"{_US_NAME_CACHE_PREFIX}:{sym}", name, ex=_US_NAME_CACHE_TTL)
            except Exception as e:  # noqa: BLE001
                logger.warning("signal_radar_us_name_cache_write_error", symbol=sym, error=str(e))

    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": _PUBLIC_UA}) as client:
        await asyncio.gather(*(_one(client, sym) for sym in to_fetch))

    logger.info("signal_radar_us_names_resolved", requested=len(symbols),
                cached=len(symbols) - len(to_fetch), fetched=len(result) - (len(symbols) - len(to_fetch)))
    return result


# 请求头均不含任何个人信息。维基百科要求写明客户端身份；纳斯达克接口会挂起非浏览器
# 形态的请求（实测 ReadTimeout），只能用浏览器形态。
_PUBLIC_UA = "Mozilla/5.0 (compatible; DeepAlphaRadar/1.0; +https://deepalpha.club)"
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def clean_us_name(name: str) -> str:
    """纳斯达克列表的公司全称 → 简短展示名（去掉 Inc./Corporation、Class A Common Stock 等尾巴）。"""
    s = re.sub(r"\s+Class\s+[A-C]\s+(Common|Ordinary|Capital)\s+(Stock|Shares).*$", "", name.strip())
    s = re.sub(r"\s+(Common|Ordinary|Capital)\s+(Stock|Shares).*$", "", s)
    s = re.sub(r"\s+American Depositary Shares.*$", "", s)
    s = re.sub(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Ltd\.?|Limited|plc|N\.V\.)$", "", s)
    s = re.sub(r",?\s+Company$", "", s)
    return s.strip() or name.strip()


def parse_nasdaq100(payload: object) -> list[tuple[str, str, float]]:
    """解析纳斯达克官方成分列表 JSON（data.data.rows[{symbol, companyName}]）。"""
    try:
        rows = payload["data"]["data"]["rows"]  # type: ignore[index]
    except (TypeError, KeyError):
        return []
    out: list[tuple[str, str, float]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").strip().upper()
        if sym:
            out.append((sym, clean_us_name(str(r.get("companyName") or sym)), 0.0))
    return out


def parse_wiki_sp500(html: str) -> list[tuple[str, str, float]]:
    """解析维基百科标普500 成分表（Symbol / Security 列）。代码里的 . 换成 -（BRK.B → BRK-B，行情源形态）。"""
    import io

    import pandas as pd

    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return []
    for tbl in tables:
        cols = [str(c) for c in tbl.columns]
        if "Symbol" in cols and "Security" in cols and len(tbl) > 90:
            return [(str(s).strip().replace(".", "-"), str(n).strip(), 0.0)
                    for s, n in zip(tbl["Symbol"], tbl["Security"], strict=False) if str(s).strip()]
    return []


async def _fetch_nasdaq100() -> list[tuple[str, str, float]]:
    """纳斯达克官方纳指100 成分列表，失败返回空列表。"""
    url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": _BROWSER_UA, "Accept": "application/json"}) as c:
            resp = await c.get(url)
        if resp.status_code != 200:
            logger.warning("signal_radar_nasdaq100_http_error", status=resp.status_code)
            return []
        rows = parse_nasdaq100(resp.json())
        logger.info("signal_radar_nasdaq100_fetched", count=len(rows))
        return rows
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_nasdaq100_fetch_error", error=str(e))
        return []


async def _fetch_wiki_sp500() -> list[tuple[str, str, float]]:
    """维基百科标普500 成分表，失败返回空列表。"""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": _PUBLIC_UA},
                                     follow_redirects=True) as c:
            resp = await c.get(url)
        if resp.status_code != 200:
            logger.warning("signal_radar_wiki_sp500_http_error", status=resp.status_code)
            return []
        rows = await asyncio.to_thread(parse_wiki_sp500, resp.text)
        logger.info("signal_radar_wiki_sp500_fetched", count=len(rows))
        return rows
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_wiki_sp500_fetch_error", error=str(e))
        return []


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
    raw: list[tuple[str, str, float]], zh_names: dict[str, str], *, max_scan: int,
    fallback_to_source_name: bool = True,
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
        resolved.append((clean, zh_names.get(clean, name if fallback_to_source_name else "")))
        if len(resolved) >= max_scan:
            break
    return resolved


async def _fetch_dynamic(universe: MarketUniverse) -> list[tuple[str, str, float]]:
    """按 universe 的来源策略动态拉取原始成分。"""
    if universe.source == SOURCE_NASDAQ100:
        return await _fetch_nasdaq100()
    if universe.source == SOURCE_WIKI_SP500:
        return await _fetch_wiki_sp500() or await _fetch_fmp_sp500()
    if universe.source == SOURCE_FMP_SP500:
        return await _fetch_fmp_sp500()
    if universe.source == SOURCE_AKSHARE_INDEX:
        return await _fetch_akshare_index(universe.source_arg)
    # etf_holdings：A 股/港股 ETF 用 FMP 代码形态
    etf = universe.etf_symbol if universe.market == "us" else _safe_fmp_symbol(universe.etf_symbol)
    return await _fetch_fmp_holdings(etf) if etf else []


async def resolve_constituents(
    market: str, *, redis: Redis, universe_key: str | None = None, refresh: bool = False,
) -> list[tuple[str, str]]:
    """解析某 (市场, universe) 的扫描成分股：缓存 → 动态来源 → 静态兜底。

    refresh=True（用户主动刷新）跳过成分股缓存重新解析，让之前没解析出中文名的标的
    有机会补上；已解析成功的美股中文名有独立 30 天缓存，不会重复查询。
    """
    universe = get_universe(market, universe_key)
    if universe is None:
        return []

    cache_key = f"{_CACHE_PREFIX}:{universe.market}:{universe.key}"
    cached = None
    if not refresh:
        try:
            cached = await redis.get(cache_key)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_constituents_cache_read_error", market=market, error=str(e))
    if cached:
        try:
            pairs = json.loads(cached)
            return [(str(s), str(n)) for s, n in pairs]
        except Exception:  # noqa: BLE001
            pass

    raw = await _fetch_dynamic(universe)
    # 中文名：先用本 universe 的 curated 名，再查同市场其他 universe 的（纳指/标普互补）
    zh = _zh_name_map(universe)
    clean_symbols: list[str] = []
    for sym, _, _ in raw:
        try:
            _, clean = normalize(sym)
        except InvalidSymbolError:
            continue
        clean_symbols.append(clean)
        if clean not in zh and (name := resolve_name(universe.market, clean)):
            zh[clean] = name
    if universe.market == "us":
        # curated 清单只覆盖几十只龙头；其余的查东方财富美股中文名，覆盖面广得多
        missing = [s for s in clean_symbols if s not in zh]
        if missing:
            zh.update(await _resolve_us_names(missing, redis=redis))
    # 美股查不到中文名（东方财富也没有）时名称留空（气泡只显示代码），英文全称太长不展示
    resolved = _map_to_universe(raw, zh, max_scan=universe.max_scan,
                                fallback_to_source_name=universe.market != "us")

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
