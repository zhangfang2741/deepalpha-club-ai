"""雷达按行业：成分股行业标签、每日按行业的买卖点统计与行业信号池。

行业 key 与 regime 行业状态一致（app/services/regime/constants.SECTORS），这样行业弹层点哪个行业，
雷达就能筛出同一个行业的气泡。美股：标普1500 的 GICS 板块（复用基本面研究的成分表缓存），严格按 GICS 一级行业，半导体属信息技术，不单列。
A 股：用本土的申万一级（31 个，key 即中文名，如「电子」「银行」），不套 GICS；东财行业名即申万二级，
经 `quant_research/cnhk/sectors.py` 的 `CN_INDUSTRY_TO_SW` 归到一级。港股：东财行业经映射归到 GICS 一级。
A 股 / 港股整市场一次取、Redis 缓存 24 小时。

每日快照只存前 N 个气泡，按行业筛选不能在它上面做——组装快照时（基本面排雷之后、截取前 N 之前）
按行业各留一份前 N，存单独的键 signal_radar:sector:{口径}:{市场}:{universe}:{日期}，不撑大主缓存。
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.signal_radar import RadarSignalOut

# GICS 板块 → regime 行业 key
GICS_TO_SECTOR: dict[str, str] = {
    "information_technology": "technology",
    "consumer_discretionary": "discretionary",
    "communication_services": "communication",
    "financials": "financials",
    "industrials": "industrials",
    "energy": "energy",
    "materials": "materials",
    "health_care": "healthcare",
    "consumer_staples": "staples",
    "utilities": "utilities",
    "real_estate": "realestate",
}

# 行业筛选用的宽基 universe（科技指数成分几乎都在科技，按行业筛没有意义）
BROAD_UNIVERSE: dict[str, str] = {"us": "sp500", "cn": "csi300", "hk": "hsi"}

SECTOR_POOL_PREFIX = "signal_radar:sector"
CNHK_TAGS_PREFIX = "signal_radar:sector_tags"
CNHK_TAGS_TTL = 3600 * 24
# 整市场元数据取数少于这个只数视为残缺（数据源限流 / 繁忙），不用也不缓存
_CNHK_MIN_TAGS = {"cn": 1000, "hk": 200}


def us_tags_from_sp1500(sp1500: dict[str, tuple[str, str]]) -> dict[str, str]:
    """{symbol: (name, gics_key)} → {symbol: 行业 key}。"""
    out: dict[str, str] = {}
    for symbol, (_, gics) in sp1500.items():
        key = GICS_TO_SECTOR.get(gics)
        if key is None:
            continue
        out[symbol] = key
    return out


def cn_tags_from_meta(meta: dict[str, object]) -> dict[str, str]:
    """{代码: CnMeta} → {代码: 申万一级行业名}；行业未映射的不打标签。"""
    from app.services.quant_research.cnhk.sectors import cn_sw_industry

    out: dict[str, str] = {}
    for code, m in meta.items():
        key = cn_sw_industry(getattr(m, "industry", None))
        if key:
            out[code] = key
    return out


def hk_tags_from_meta(meta: dict[str, object]) -> dict[str, str]:
    """{代码: HkMeta} → {代码: GICS 行业 key}；行业未映射的不打标签。"""
    out: dict[str, str] = {}
    for code, m in meta.items():
        key = GICS_TO_SECTOR.get(getattr(m, "sector", None) or "")
        if key:
            out[code] = key
    return out


async def _fetch_cnhk_tags(market: str) -> dict[str, str]:
    from app.services.quant_research.cnhk import cn_source, hk_source
    from app.services.quant_research.cnhk.http import _UA

    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": _UA}, trust_env=False) as client:
        if market == "cn":
            return cn_tags_from_meta(await cn_source.fetch_market_meta(client))  # type: ignore[arg-type]
        today = datetime.now(UTC).date()
        return hk_tags_from_meta(await hk_source.fetch_meta(client, today))  # type: ignore[arg-type]


async def _load_cnhk_tags(market: str, redis: Redis | None) -> dict[str, str]:
    key = f"{CNHK_TAGS_PREFIX}:{market}"
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_sector_tags_cache_read_failed", market=market, error=str(e))
    tags = await _fetch_cnhk_tags(market)
    if len(tags) < _CNHK_MIN_TAGS[market]:
        logger.warning("signal_radar_sector_tags_incomplete", market=market, count=len(tags))
        return {}
    if redis is not None:
        try:
            await redis.set(key, json.dumps(tags, ensure_ascii=False), ex=CNHK_TAGS_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_sector_tags_cache_write_failed", market=market, error=str(e))
    return tags


async def load_sector_tags(market: str, redis: Redis | None) -> dict[str, str]:
    """成分股 → 行业 key；没有该市场的分类或取数失败返回空（雷达照常，只是不出行业统计）。"""
    try:
        if market == "us":
            from app.services.quant_research.universe import fetch_sp1500

            return us_tags_from_sp1500(await fetch_sp1500(redis))
        if market in _CNHK_MIN_TAGS:
            return await _load_cnhk_tags(market, redis)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sector_tags_failed", market=market, error=str(e))
    return {}


_MARKET_SUFFIX = re.compile(r"(\.(SH|SZ|SS|BJ|HK)|^(SH|SZ|BJ|HK))$", re.I)


def lookup_tag(tags: dict[str, str], symbol: str) -> str | None:
    """按代码查行业：美股规范化 BRK.B → BRK-B；港股 0700 补成 5 位 00700。"""
    hit = tags.get(symbol)
    if hit:
        return hit
    clean = _MARKET_SUFFIX.sub("", symbol.upper())
    if clean.isdigit() and len(clean) < 5:
        clean = clean.zfill(5)
    return tags.get(clean) or tags.get(symbol.upper().replace(".", "-"))


def tag_signals(signals: list[RadarSignalOut], tags: dict[str, str]) -> list[RadarSignalOut]:
    """给信号写上 sector（原地），返回同一列表。美股代码按成分表规范化（BRK.B → BRK-B）。"""
    for s in signals:
        s.sector = lookup_tag(tags, s.symbol)
    return signals


def sector_counts(signals: list[RadarSignalOut]) -> dict[str, dict[str, int]]:
    """{行业: {"buy": n, "sell": m}}；没有行业标签的信号不计入。"""
    out: dict[str, dict[str, int]] = {}
    for s in signals:
        if not s.sector:
            continue
        c = out.setdefault(s.sector, {"buy": 0, "sell": 0})
        c["buy" if s.side == "buy" else "sell"] += 1
    return out


def group_by_sector(signals: list[RadarSignalOut]) -> dict[str, list[RadarSignalOut]]:
    """按行业分组；没有行业标签的信号丢弃。"""
    out: dict[str, list[RadarSignalOut]] = {}
    for s in signals:
        if s.sector:
            out.setdefault(s.sector, []).append(s)
    return out


def merge_sub_levels(pools: dict[str, list[RadarSignalOut]], ranked: list[RadarSignalOut]) -> None:
    """把已补算的次级别结论（最新一天入榜气泡）同步到行业池里的同一信号。"""
    verdicts = {(s.symbol, s.signal_type, s.date): (s.sub_level_verdict, s.sub_level_label)
                for s in ranked if s.sub_level_verdict}
    for signals in pools.values():
        for s in signals:
            hit = verdicts.get((s.symbol, s.signal_type, s.date))
            if hit:
                s.sub_level_verdict, s.sub_level_label = hit


def pool_key(mode_ns: str, market: str, universe: str, day: str) -> str:
    """行业池的 Redis 键。"""
    return f"{SECTOR_POOL_PREFIX}:{mode_ns}:{market}:{universe}:{day}"


async def write_pools(redis: Redis, mode_ns: str, market: str, universe: str,
                      pools_by_day: dict[str, dict[str, list[RadarSignalOut]]], ttl: int) -> None:
    """把每天的行业池写进各自的键。"""
    for day, pools in pools_by_day.items():
        payload = {k: [s.model_dump(mode="json") for s in v] for k, v in pools.items()}
        try:
            await redis.set(pool_key(mode_ns, market, universe, day), json.dumps(payload, ensure_ascii=False), ex=ttl)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_sector_pool_write_failed", market=market, day=day, error=str(e))


async def read_pools(redis: Redis, mode_ns: str, market: str, universe: str,
                     day: str) -> dict[str, list[RadarSignalOut]] | None:
    """当天全部行业池 {行业: 前 N 个气泡}；None = 这一天没有行业池（旧快照 / 该市场没有行业分类 / 读失败）。"""
    try:
        raw = await redis.get(pool_key(mode_ns, market, universe, day))
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sector_pool_read_failed", market=market, day=day, error=str(e))
        return None
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return {k: [RadarSignalOut.model_validate(x) for x in v] for k, v in data.items()}
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sector_pool_bad_json", market=market, day=day, error=str(e))
        return None


async def read_pool(redis: Redis, mode_ns: str, market: str, universe: str, day: str,
                    sector: str) -> list[RadarSignalOut] | None:
    """None = 这一天没有行业池（旧快照 / 该市场没有行业分类）；[] = 有池但该行业当天没有信号。"""
    pools = await read_pools(redis, mode_ns, market, universe, day)
    return None if pools is None else pools.get(sector, [])
