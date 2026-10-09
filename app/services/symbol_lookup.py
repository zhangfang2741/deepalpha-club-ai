"""按名称 / 代码搜股票，供缠论分析页搜索框联想（A 股 / 港股 / 美股中文名）。

名单来源：A 股、港股用东财全市场名单（Redis 缓存 24 小时）；取不到时退回信号雷达里写死的
curated 成分（只有几十到几百只，但保证搜索框不报错）。美股：含中文先查 curated 中文名，
纯英文再叫 FMP 联想，两边合并、有中文名的用中文名。
"""
from __future__ import annotations

import asyncio
import time

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
# 冷缓存时最多等多久：A 股全市场名单冷拉要十几秒（iOS 请求会超时、列表就是空的），
# 超过这个时间先用写死的成分兜底答复，名单在后台继续拉，拉完下一次搜索就是全量。
_WAIT_BUDGET = 1.5
# 拉取失败后这段时间内不再重试（数据源挂了时别每次输入都去打一遍）
_FAIL_COOLDOWN = 30.0

_MEM: dict[str, tuple[float, dict[str, str]]] = {}  # 进程内缓存：{市场: (时间, 名单)}，Redis 不可用时也能秒回
_INFLIGHT: dict[str, asyncio.Task] = {}  # 单飞：同一市场同一时刻只拉一次
_FAILED_AT: dict[str, float] = {}


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


def _mem_get(market: str) -> dict[str, str] | None:
    item = _MEM.get(market)
    if item and time.monotonic() - item[0] < _CACHE_TTL:
        return item[1]
    return None


async def _load_full(market: str, redis: Redis | None) -> dict[str, str] | None:
    """拉全市场名单并写缓存；失败 / 残缺返回 None（不缓存）。在后台任务里跑，不抛异常。"""
    try:
        table = await _fetch_name_table(market)
    except Exception as e:  # noqa: BLE001 — 数据源挂了不能让搜索框报错
        logger.warning("symbol_search_names_fetch_failed", market=market, error=str(e))
        _FAILED_AT[market] = time.monotonic()
        return None
    if len(table) < _MIN_COUNT.get(market, 1):
        logger.warning("symbol_search_names_incomplete", market=market, count=len(table))
        _FAILED_AT[market] = time.monotonic()
        return None
    _MEM[market] = (time.monotonic(), table)
    if redis is not None:
        try:
            await set_json(redis, f"{_CACHE_PREFIX}:{market}", table, expire=_CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("symbol_search_cache_write_failed", market=market, error=str(e))
    return table


def _ensure_loading(market: str, redis: Redis | None) -> asyncio.Task | None:
    """后台拉取任务（单飞）；刚失败过且在冷却期内返回 None。"""
    task = _INFLIGHT.get(market)
    if task is not None and not task.done():
        return task
    if time.monotonic() - _FAILED_AT.get(market, -1e9) < _FAIL_COOLDOWN:
        return None
    task = asyncio.create_task(_load_full(market, redis))
    _INFLIGHT[market] = task

    def _cleanup(t: asyncio.Task, m: str = market) -> None:
        if _INFLIGHT.get(m) is t:
            _INFLIGHT.pop(m, None)

    task.add_done_callback(_cleanup)
    return task


async def load_name_table(market: str, redis: Redis | None, *, wait: float = _WAIT_BUDGET) -> dict[str, str]:
    """{代码: 名称}。内存 → Redis → 后台拉取（最多等 wait 秒，等不到先用 curated 兜底，不抛异常）。"""
    mem = _mem_get(market)
    if mem:
        return mem
    if redis is not None:
        try:
            cached = await get_json(redis, f"{_CACHE_PREFIX}:{market}")
            if cached:
                _MEM[market] = (time.monotonic(), cached)
                return cached
        except Exception as e:  # noqa: BLE001 — 缓存挂了照样现取
            logger.warning("symbol_search_cache_read_failed", market=market, error=str(e))
    task = _ensure_loading(market, redis)
    if task is not None:
        try:
            table = await asyncio.wait_for(asyncio.shield(task), timeout=wait)
            if table:
                return table
        except asyncio.TimeoutError:
            logger.info("symbol_search_names_still_loading", market=market)
    return _curated(market)


async def prewarm(redis: Redis | None = None) -> None:
    """启动时后台预热 A 股 / 港股名单，用户第一次搜索时缓存已经是热的。"""
    for market in ("cn", "hk"):
        await load_name_table(market, redis, wait=180)


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


async def search(market: str, query: str, *, redis: Redis | None = None, limit: int = 10,
                 wait: float = _WAIT_BUDGET) -> list[dict]:
    """返回 [{market, symbol, name}]，最多 limit 条；market 为 us / cn / hk。"""
    q = (query or "").strip()
    if not q:
        return []
    if market == "us":
        return await _search_us(q, redis, limit)
    table = await load_name_table(market, redis, wait=wait)
    return [{"market": market, "symbol": c, "name": n} for c, n in rank_matches(table, q, limit)]
