"""雷达按行业：成分股行业标签、每日按行业的买卖点统计与行业信号池。

行业 key 与 regime 行业状态一致（app/services/regime/constants.SECTORS），这样行业弹层点哪个行业，
雷达就能筛出同一个行业的气泡。第一期只有美股：标普1500 的 GICS 板块（复用基本面研究的成分表缓存），
半导体从信息技术里单独拆出（regime 把半导体当独立行业）。

每日快照只存前 N 个气泡，按行业筛选不能在它上面做——组装快照时（基本面排雷之后、截取前 N 之前）
按行业各留一份前 N，存单独的键 signal_radar:sector:{口径}:{市场}:{universe}:{日期}，不撑大主缓存。
"""
from __future__ import annotations

import json

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

# 标普1500 里 GICS 子行业为半导体 / 半导体设备的主要成分（成分稳定，人工维护）
US_SEMICONDUCTORS: frozenset[str] = frozenset({
    "NVDA", "AVGO", "AMD", "QCOM", "TXN", "INTC", "MU", "ADI", "AMAT", "LRCX", "KLAC", "MCHP",
    "NXPI", "ON", "MPWR", "SWKS", "TER", "QRVO", "ENTG", "MRVL", "MKSI", "LSCC", "SLAB", "CRUS",
    "SYNA", "POWI", "AMKR", "OLED", "RMBS", "ONTO", "COHU", "FORM", "DIOD", "SMTC", "ACLS",
    "KLIC", "UCTT", "ICHR", "AOSL", "MXL", "ALGM", "WOLF", "FSLR", "ENPH",
})

# 行业筛选用的宽基 universe（科技指数成分几乎都在科技 / 半导体，按行业筛没有意义）
BROAD_UNIVERSE: dict[str, str] = {"us": "sp500", "cn": "csi300", "hk": "hsi"}

SECTOR_POOL_PREFIX = "signal_radar:sector"


def us_tags_from_sp1500(sp1500: dict[str, tuple[str, str]]) -> dict[str, str]:
    """{symbol: (name, gics_key)} → {symbol: 行业 key}。"""
    out: dict[str, str] = {}
    for symbol, (_, gics) in sp1500.items():
        key = GICS_TO_SECTOR.get(gics)
        if key is None:
            continue
        out[symbol] = "semiconductors" if symbol in US_SEMICONDUCTORS else key
    return out


async def load_sector_tags(market: str, redis: Redis | None) -> dict[str, str]:
    """成分股 → 行业 key；没有该市场的分类或取数失败返回空（雷达照常，只是不出行业统计）。"""
    if market != "us":
        return {}
    from app.services.quant_research.universe import fetch_sp1500

    try:
        return us_tags_from_sp1500(await fetch_sp1500(redis))
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sector_tags_failed", market=market, error=str(e))
        return {}


def tag_signals(signals: list[RadarSignalOut], tags: dict[str, str]) -> list[RadarSignalOut]:
    """给信号写上 sector（原地），返回同一列表。美股代码按成分表规范化（BRK.B → BRK-B）。"""
    for s in signals:
        s.sector = tags.get(s.symbol) or tags.get(s.symbol.upper().replace(".", "-"))
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


async def read_pool(redis: Redis, mode_ns: str, market: str, universe: str, day: str,
                    sector: str) -> list[RadarSignalOut] | None:
    """None = 这一天没有行业池（旧快照 / 该市场没有行业分类）；[] = 有池但该行业当天没有信号。"""
    try:
        raw = await redis.get(pool_key(mode_ns, market, universe, day))
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sector_pool_read_failed", market=market, day=day, error=str(e))
        return None
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return [RadarSignalOut.model_validate(x) for x in data.get(sector, [])]
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sector_pool_bad_json", market=market, day=day, error=str(e))
        return None
