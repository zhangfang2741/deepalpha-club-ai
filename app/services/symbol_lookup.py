"""按名称 / 代码搜股票，供缠论分析页搜索框联想（A 股 / 港股 / 美股中文名）。

名单来源：A 股、港股用东财全市场名单（Redis 缓存 24 小时）；取不到时退回信号雷达里写死的
curated 成分（只有几十到几百只，但保证搜索框不报错）。美股：含中文先查 curated 中文名，
纯英文再叫 FMP 联想，两边合并、有中文名的用中文名。
"""
from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.services.signal_radar.universe import _NAME_BY_MARKET
from app.services.skills.symbol_search import search_us_symbols

_CACHE_PREFIX = "symbol_search:names:v1"
_CACHE_TTL = 3600 * 24
# 取回过少视为残缺：不缓存、不用，退回 curated（A 股约 5400 只、港股约 2600 只）
_MIN_COUNT = {"cn": 3000, "hk": 1000}


def _norm_code(code: str) -> str:
    return code.strip().upper()


def rank_matches(table: dict[str, str], query: str, limit: int) -> list[tuple[str, str]]:
    """在 {代码: 名称} 里按相关度挑前 limit 条。

    优先级：代码精确 > 代码前缀 > 名称前缀 > 名称包含 > 代码包含；同级按代码排序（结果稳定）。
    数字查询忽略前导 0（港股 700 也能找到 0700）。
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    q_digits = q.lstrip("0") if q.isdigit() else None
    scored: list[tuple[int, str, str]] = []
    for code, name in table.items():
        c, n = code.lower(), name.lower()
        c_stripped = c.lstrip("0") if c.isdigit() else c
        if c == q or (q_digits and c_stripped == q_digits):
            score = 0
        elif c.startswith(q) or (q_digits and c_stripped.startswith(q_digits)):
            score = 1
        elif n.startswith(q):
            score = 2
        elif q in n:
            score = 3
        elif q in c:
            score = 4
        else:
            continue
        scored.append((score, code, name))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [(code, name) for _, code, name in scored[:limit]]


async def _fetch_name_table(market: str) -> dict[str, str]:
    """东财全市场 {裸代码: 名称}。"""
    from app.services.quant_research.cnhk import cn_source
    from app.services.quant_research.cnhk import eastmoney as em
    from app.services.quant_research.cnhk.http import _UA

    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": _UA}, trust_env=False) as client:
        if market == "cn":
            meta = await cn_source.fetch_market_meta(client)
            return {code: m.name for code, m in meta.items() if m.name}
        rows = await em.table(client, "RPT_HKF10_INFO_SECURITYINFO", "SECURITY_CODE,SECURITY_NAME_ABBR", None)
        out: dict[str, str] = {}
        for r in rows:
            raw = str(r.get("SECURITY_CODE") or "").strip()
            name = str(r.get("SECURITY_NAME_ABBR") or "").strip()
            if raw.isdigit() and name:
                out[raw.lstrip("0").zfill(4)] = name  # 00700 → 0700，与 App / 雷达的写法对齐
        return out


def _curated(market: str) -> dict[str, str]:
    return dict(_NAME_BY_MARKET.get(market, {}))


async def load_name_table(market: str, redis: Redis | None) -> dict[str, str]:
    """{代码: 名称}；全市场名单取不到或残缺时退回 curated，不缓存残缺结果。"""
    key = f"{_CACHE_PREFIX}:{market}"
    if redis is not None:
        try:
            cached = await get_json(redis, key)
            if cached:
                return cached
        except Exception as e:  # noqa: BLE001 — 缓存挂了照样现取
            logger.warning("symbol_search_cache_read_failed", market=market, error=str(e))
    try:
        table = await _fetch_name_table(market)
    except Exception as e:  # noqa: BLE001 — 数据源挂了不能让搜索框报错
        logger.warning("symbol_search_names_fetch_failed", market=market, error=str(e))
        return _curated(market)
    if len(table) < _MIN_COUNT.get(market, 1):
        logger.warning("symbol_search_names_incomplete", market=market, count=len(table))
        return _curated(market)
    if redis is not None:
        try:
            await set_json(redis, key, table, expire=_CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("symbol_search_cache_write_failed", market=market, error=str(e))
    return table


async def _search_us(query: str, redis: Redis | None, limit: int) -> list[dict]:
    curated = _curated("us")
    hits = [{"market": "us", "symbol": c, "name": n} for c, n in rank_matches(curated, query, limit)]
    if query.isascii():  # 英文 / 代码才值得问 FMP；中文名它查不到
        try:
            extra = await search_us_symbols(query, redis=redis, limit=limit)
        except Exception as e:  # noqa: BLE001
            logger.warning("symbol_search_us_fmp_failed", error=str(e))
            extra = []
        seen = {h["symbol"] for h in hits}
        for r in extra:
            sym = _norm_code(r["symbol"])
            if sym not in seen:
                seen.add(sym)
                hits.append({"market": "us", "symbol": sym, "name": curated.get(sym) or r.get("name") or sym})
    return hits[:limit]


async def search(market: str, query: str, *, redis: Redis | None = None, limit: int = 10) -> list[dict]:
    """返回 [{market, symbol, name}]，最多 limit 条；market 为 us / cn / hk。"""
    q = (query or "").strip()
    if not q:
        return []
    if market == "us":
        return await _search_us(q, redis, limit)
    table = await load_name_table(market, redis)
    return [{"market": market, "symbol": c, "name": n} for c, n in rank_matches(table, q, limit)]
