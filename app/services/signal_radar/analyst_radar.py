"""评级雷达（分析师评级）：最近 1 周 / 1 个月 / 3 个月里被券商净上调、净下调评级的公司，按圈放进同心环。

数据同 `analyst_events`：FMP 个股评级变动（券商、日期、前后评级、动作），只有美股；维持评级不算。逐只拉取较慢（标普 500 约 4 分钟），
所以只读 Redis 缓存、缺失 / 过期的由后台补，响应的 `pending_symbols` 是还在补的只数。

规则：某只股票在窗口（7 / 30 / 90 天）里「上调家数 - 下调家数」> 0 记一条上调（`analyst_up`，App 画红），< 0 记一条下调（`analyst_down`，画绿），
按**最小的**满足条件的窗口放圈；一只股票上调、下调各可以有一条。幅度 = 净家数，同家数里越近的略大一点（只作先后）。
「精选」沿用基本面雷达的门槛：综合等级达到本股票池的「好股票」门槛（`choose_cutoff`）。只陈列事实、不是推荐。
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.quant_research import AnalystChangeOut, AnalystRadarOut, TrendFacts, TrendRadarItem
from app.services.quant_research import repository
from app.services.quant_research.grading import GRADE_ORDER
from app.services.quant_research.markets import normalize_symbol
from app.services.signal_radar import analyst_events as ae
from app.services.signal_radar import sectors
from app.services.signal_radar.quality_view import choose_cutoff

RINGS = (7, 30, 90)
PER_KIND_LIMIT = 60
GRADE_LOOKBACK_DAYS = 14        # 取每只股票最近这么多天内最新的一份综合等级


def _side(actions: list[dict], as_of: date, up: bool) -> tuple[int, int, int, list[dict]] | None:
    """(圈, 窗口内上调家数, 下调家数, 这一方向的动作新到旧)；净值方向不对 / 没有返回 None。"""
    want = "upgrade" if up else "downgrade"
    for ring in RINGS:
        since = as_of - timedelta(days=ring)
        ups, downs = ae.net_counts(actions, since)
        if (ups - downs > 0) if up else (ups - downs < 0):
            side = sorted((a for a in actions if a["action"] == want and since.isoformat() <= a["date"] <= as_of.isoformat()),
                          key=lambda a: a["date"], reverse=True)
            if side:
                return ring, ups, downs, side
    return None


_SIDES: tuple[tuple[bool, Literal["analyst_up", "analyst_down"]], ...] = ((True, "analyst_up"), (False, "analyst_down"))


def build_analyst_radar(
    history: dict[str, list[dict]], *, names: dict[str, str], grades: dict[str, str | None], tags: dict[str, str],
    as_of: date, market: str, pending: int = 0, supported: bool = True,
) -> AnalystRadarOut:
    """history：{代码: 评级变动动作（新到旧）}；grades：{代码: 综合等级}；tags：代码 → 雷达行业 key。"""
    rated = [g for g in grades.values() if g in GRADE_ORDER]
    cutoff = choose_cutoff(rated) if rated else None
    cutoff_rank = GRADE_ORDER.index(cutoff) if cutoff else None
    buckets: dict[str, list[TrendRadarItem]] = {"analyst_up": [], "analyst_down": []}
    for symbol, actions in history.items():
        grade = grades.get(symbol)
        good = cutoff_rank is not None and grade in GRADE_ORDER and GRADE_ORDER.index(grade or "") <= cutoff_rank
        for up, kind in _SIDES:
            hit = _side(actions, as_of, up)
            if hit is None:
                continue
            ring, ups, downs, side = hit
            net = abs(ups - downs)
            age = max(0, (as_of - date.fromisoformat(side[0]["date"])).days)
            magnitude = round(net + max(0.0, 1 - age / RINGS[-1]) * 0.09, 2)     # 零头 < 0.1，只在同家数里分先后
            firms: list[str] = []
            for a in side:
                if a["firm"] and a["firm"] not in firms:
                    firms.append(a["firm"])
            buckets[kind].append(TrendRadarItem(
                symbol=symbol, name=names.get(symbol, symbol), grade=grade, kind=kind, ring_days=ring,
                strength=float(net), magnitude=magnitude, good=bool(good), sector=sectors.lookup_tag(tags, symbol),
                analyst=AnalystChangeOut(up=ups, down=downs, window_days=ring, last_date=side[0]["date"],
                                         firms=firms[: ae.MAX_FIRMS], to_bucket=ae.bucket_of(side[0]["new"])),
                facts=TrendFacts()))
    items: list[TrendRadarItem] = []
    counts: dict[str, int] = {}
    for kind, lst in buckets.items():
        lst.sort(key=lambda i: (i.ring_days, -i.strength, -i.magnitude, i.symbol))
        # 达标的与未达标的各取 PER_KIND_LIMIT 个，互不挤占
        keep = [i for i in lst if i.good][:PER_KIND_LIMIT] + [i for i in lst if not i.good][:PER_KIND_LIMIT]
        keep.sort(key=lambda i: (i.ring_days, -i.strength, -i.magnitude, i.symbol))
        items += keep
        counts[kind] = len(keep)
        counts[f"{kind}_good"] = sum(i.good for i in keep)
    return AnalystRadarOut(
        market=market, as_of=as_of.isoformat(), rings=list(RINGS), thresholds={"analyst_min_net": 1.0},
        items=items, counts=counts, good_grade=cutoff, pending_symbols=pending, supported=supported)


async def _grades_for(market: str, pairs: list[tuple[str, str]], end: date) -> dict[str, str | None]:
    """{雷达代码: 最新综合等级}；读取失败返回空（只是都不算精选，不影响评级雷达本身）。"""
    from app.services.signal_radar.quant_filter import grade_from_row

    try:
        stored = {s: normalize_symbol(market, s) for s, _ in pairs}
        rows = await repository.get_latest_quant_grades(
            market, sorted(set(stored.values())), end - timedelta(days=GRADE_LOOKBACK_DAYS), end)
    except Exception:  # noqa: BLE001
        logger.exception("signal_radar_analyst_radar_grades_failed", market=market)
        return {}
    by_stored = {r.symbol: g.grade for r in rows if (g := grade_from_row(r)) is not None}
    return {s: by_stored.get(n) for s, n in stored.items()}


async def analyst_radar(
    market: str, pairs: list[tuple[str, str]], scope: str, *, redis: Redis, now: datetime | None = None,
) -> AnalystRadarOut:
    """pairs：[(代码, 名称)] 股票池（指数成分股或自选）；scope：后台补拉的锁范围。非美股 supported=False。"""
    now = now or datetime.now(UTC)
    if market not in ae.SUPPORTED_MARKETS:
        return build_analyst_radar({}, names={}, grades={}, tags={}, as_of=now.date(), market=market, supported=False)
    names = {s: n for s, n in pairs}
    symbols = sorted(names)
    try:
        cached = await ae.cached_with_refresh(market, f"radar:{scope}", symbols, redis, now)
    except Exception:
        logger.exception("signal_radar_analyst_radar_read_failed", market=market)
        cached = {}
    tags = await sectors.load_sector_tags(market, redis)
    grades = await _grades_for(market, pairs, now.date())
    history = {s: cached[s]["actions"] for s in symbols if s in cached}
    return build_analyst_radar(history, names=names, grades=grades, tags=tags, as_of=now.date(), market=market,
                               pending=sum(1 for s in symbols if s not in cached))


_CACHE_TTL = 2 * 3600
_PENDING_TTL = 60


def _cache_key(market: str, scope: str) -> str:
    return f"signal_radar:analyst_radar:v1:{market}:{scope}"


async def cached_analyst_radar(
    market: str, pairs: list[tuple[str, str]], scope: str, *, redis: Redis, refresh: bool = False,
) -> AnalystRadarOut:
    """评级雷达的缓存入口：用户请求只读缓存（后台每小时 `refresh=True` 重算一次写回），缓存没有才现算。

    后台还在补拉券商数据（pending_symbols > 0）时只缓存 1 分钟，补齐后才缓存 2 小时。自选因人而异，不走这里（直接 analyst_radar）。
    """
    key = _cache_key(market, scope)
    if not refresh:
        try:
            if cached := await get_json(redis, key):
                return AnalystRadarOut(**cached)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_analyst_radar_cache_read_failed", market=market, error=str(e))
    out = await analyst_radar(market, pairs, scope, redis=redis)
    try:
        await set_json(redis, key, out.model_dump(mode="json"),
                       expire=_PENDING_TTL if out.pending_symbols else _CACHE_TTL)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_analyst_radar_cache_write_failed", market=market, error=str(e))
    return out
