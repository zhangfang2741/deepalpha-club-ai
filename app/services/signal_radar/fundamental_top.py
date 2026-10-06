"""雷达「基本面研究」tab：股票池里当前综合等级最高的若干只股票。

不按日期：取每只股票最新一个评级日的综合等级，按等级（A+ 最高）再按综合分排序，返回前 N 只（画布画前 10，其余点「查看全部」）。
分析师评级只作角标（美股）：近 90 天券商净上调 / 下调家数，由 analyst_events 的缓存读出；这些前 N 只里缓存缺失 / 过期的
交给后台补（批量额度、带锁），响应 analyst_pending 为还在补的只数。**只陈列事实**：不推荐、不打买卖标签。
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.signal_radar import RadarFundamentalItemOut, RadarFundamentalResponse
from app.services.quant_research import repository
from app.services.quant_research.grading import GRADE_ORDER
from app.services.quant_research.markets import normalize_symbol
from app.services.signal_radar import analyst_events, sectors
from app.services.signal_radar.constituents import resolve_constituents
from app.services.signal_radar.quant_filter import QuantGrade, grade_from_row
from app.services.signal_radar.universe import get_universe

DEFAULT_LIMIT = 50
LOOKBACK_DAYS = 14          # 最新评级日不早于这么多天前（节假日 / 批量漏跑期间不拿过旧的评级冒充当前）
ANALYST_WINDOW_DAYS = 90


def rank_latest(history: dict[str, list[QuantGrade]]) -> list[tuple[str, QuantGrade]]:
    """每只股票取最新评级（评级日大、同日取最后写入），按等级高 → 低、综合分高 → 低、代码排序。无等级的丢弃。"""
    latest: list[tuple[str, QuantGrade]] = []
    for symbol, entries in history.items():
        valid = [g for g in entries if g.grade in GRADE_ORDER]
        if valid:
            latest.append((symbol, max(valid, key=lambda g: (g.as_of, g.available_on))))
    return sorted(latest, key=lambda t: (GRADE_ORDER.index(t[1].grade or ""), -(t[1].score if t[1].score is not None else -1), t[0]))


async def load_ranked(
    market: str, universe_key: str, redis: Redis, end: date,
) -> tuple[list[tuple[str, QuantGrade]], dict[str, str]] | None:
    """股票池每只股票最新综合等级（不早于 LOOKBACK_DAYS 天前）的排序结果 + 代码→名称。读取失败返回 None。"""
    pairs = await resolve_constituents(market, redis=redis, universe_key=universe_key)
    names = {s: n for s, n in pairs}
    try:
        stored = {s: normalize_symbol(market, s) for s in names}
        rows = await repository.get_quant_grade_history(
            market, sorted(set(stored.values())), end - timedelta(days=LOOKBACK_DAYS), end)
    except Exception:
        logger.exception("signal_radar_fundamental_top_read_failed", market=market)
        return None
    by_stored: dict[str, list[QuantGrade]] = {}
    for row in rows:
        g = grade_from_row(row)
        if g is not None and (end - g.as_of).days <= LOOKBACK_DAYS:
            by_stored.setdefault(row.symbol, []).append(g)
    history = {s: by_stored[n] for s, n in stored.items() if n in by_stored}
    return rank_latest(history), names


async def fundamental_top(
    market: str, universe_key: str | None, *, redis: Redis, limit: int = DEFAULT_LIMIT, now: datetime | None = None,
) -> RadarFundamentalResponse | None:
    """None = 不支持的 universe。评级读取失败 available=False。"""
    uni = get_universe(market, universe_key)
    if uni is None:
        return None
    now = now or datetime.now(UTC)
    end = now.date()

    def resp(**kw) -> RadarFundamentalResponse:
        return RadarFundamentalResponse(
            market=market, universe_key=uni.key, universe_name=uni.etf_name,
            analyst_supported=market in analyst_events.SUPPORTED_MARKETS, **kw)

    loaded = await load_ranked(market, uni.key, redis, end)
    if loaded is None:
        return resp(available=False)
    ranked, names = loaded
    top = ranked[:max(1, limit)]
    tags = await sectors.load_sector_tags(market, redis)

    marks: dict[str, tuple[int, int]] = {}
    pending = 0
    if market in analyst_events.SUPPORTED_MARKETS and top:
        syms = [s for s, _ in top]
        cached = await analyst_events.cached_with_refresh(market, uni.key + ":top", syms, redis, now)
        since = end - timedelta(days=ANALYST_WINDOW_DAYS)
        for s in syms:
            if s in cached:
                marks[s] = analyst_events.net_counts(cached[s]["actions"], since)
        pending = sum(1 for s in syms if s not in cached)

    items = [RadarFundamentalItemOut(
        symbol=s, name=names.get(s, s), grade=g.grade or "", score=g.score, as_of=g.as_of.isoformat(),
        sector=sectors.lookup_tag(tags, s),
        analyst_up=marks[s][0] if s in marks else None, analyst_down=marks[s][1] if s in marks else None,
    ) for s, g in top]
    newest = max((g.as_of for _, g in ranked), default=None)
    return resp(as_of=newest.isoformat() if newest else None, rated=len(ranked), items=items, analyst_pending=pending)
