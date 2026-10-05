"""雷达「基本面研究」tab：某个股票池里每天综合等级升 / 降的股票。

数据来自每日评级结果的历史（quant_results），只看综合等级（13 档字母）相邻两个评级日之间的变化；
和缠论买卖点一样是「某天出现的事实」，不打分、不排序推荐。事件日 = 新等级的评级日（as_of）。
"""
from __future__ import annotations

from datetime import date, timedelta

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.signal_radar import RadarGradeDayOut, RadarGradeEventOut, RadarGradeEventsResponse
from app.services.quant_research import repository
from app.services.quant_research.grading import GRADE_ORDER
from app.services.quant_research.markets import normalize_symbol
from app.services.signal_radar import sectors
from app.services.signal_radar.constituents import resolve_constituents
from app.services.signal_radar.quant_filter import QuantGrade, grade_from_row
from app.services.signal_radar.universe import get_universe

DEFAULT_DAYS = 10
# 某一天变档的股票超过股票池里有评级股票的这个比例，视为方法论升级 / 全员重评（不是真实的评级变化），整天不展示。
# 线上实测：2026-09-30 标普 500 有一半股票变档，之后每天约 7%。
BULK_DAY_RATIO = 0.3


def build_events(
    history: dict[str, list[QuantGrade]], names: dict[str, str], tags: dict[str, str], since: date,
    bulk_ratio: float = BULK_DAY_RATIO,
) -> list[RadarGradeDayOut]:
    """history: {雷达代码: 评级序列}。相邻评级日综合等级不同即一条事件，日期不早于 since；按日期从新到旧。"""
    by_day: dict[str, list[RadarGradeEventOut]] = {}
    for symbol, entries in history.items():
        # 同一评级日只留最后写入的一条（补跑 / 覆盖），再按评级日升序
        latest: dict[date, QuantGrade] = {}
        for g in sorted(entries, key=lambda g: g.available_on):
            latest[g.as_of] = g
        seq = [latest[d] for d in sorted(latest) if latest[d].grade in GRADE_ORDER]
        for prev, cur in zip(seq, seq[1:], strict=False):
            if cur.as_of < since or prev.grade == cur.grade:
                continue
            a, b = GRADE_ORDER.index(prev.grade or ""), GRADE_ORDER.index(cur.grade or "")
            by_day.setdefault(cur.as_of.isoformat(), []).append(RadarGradeEventOut(
                symbol=symbol, name=names.get(symbol, symbol), date=cur.as_of.isoformat(),
                direction="up" if b < a else "down", from_grade=prev.grade or "", to_grade=cur.grade or "",
                steps=abs(b - a), sector=sectors.lookup_tag(tags, symbol), score=cur.score,
            ))
    days = []
    rated = max(len(history), 1)
    for day in sorted(by_day, reverse=True):
        if len(by_day[day]) / rated > bulk_ratio:
            logger.info("signal_radar_grade_events_bulk_day_skipped", day=day, events=len(by_day[day]), rated=rated)
            continue
        events = sorted(by_day[day], key=lambda e: (-e.steps, e.symbol))
        days.append(RadarGradeDayOut(
            date=day, up_count=sum(e.direction == "up" for e in events),
            down_count=sum(e.direction == "down" for e in events), events=events))
    return days


async def grade_events(
    market: str, universe_key: str | None, *, redis: Redis, days: int = DEFAULT_DAYS, today: date | None = None,
) -> RadarGradeEventsResponse | None:
    """None = 不支持的市场 / universe。评级读取失败返回 available=False。"""
    uni = get_universe(market, universe_key)
    if uni is None:
        return None
    pairs = await resolve_constituents(market, redis=redis, universe_key=uni.key)
    names = {s: n for s, n in pairs}
    end = today or date.today()
    since = end - timedelta(days=max(1, days) + 10)       # 多留几天：节假日 / 周末评级日稀疏
    try:
        stored = {s: normalize_symbol(market, s) for s in names}
        rows = await repository.get_quant_grade_history(market, sorted(set(stored.values())), since, end)
    except Exception:
        logger.exception("signal_radar_grade_events_read_failed", market=market)
        return RadarGradeEventsResponse(market=market, universe_key=uni.key, universe_name=uni.etf_name, available=False)
    by_stored: dict[str, list[QuantGrade]] = {}
    for row in rows:
        g = grade_from_row(row)
        if g is not None:
            by_stored.setdefault(row.symbol, []).append(g)
    history = {s: by_stored[n] for s, n in stored.items() if n in by_stored}
    tags = await sectors.load_sector_tags(market, redis)
    shown_since = end - timedelta(days=max(1, days))
    return RadarGradeEventsResponse(
        market=market, universe_key=uni.key, universe_name=uni.etf_name,
        days=build_events(history, names, tags, shown_since),
    )
