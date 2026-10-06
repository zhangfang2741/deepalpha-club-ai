"""雷达「分析师评级」tab：股票池里每天被券商净上调 / 净下调评级的股票。

数据来自 FMP 个股评级变动（grades：券商、日期、前后评级、动作），只取美股；A 股 / 港股没有按日的券商评级变动，
接口返回 supported=False。和缠论买卖点、基本面升降一样是「某天出现的事实」：只陈列，不打分、不推荐。

一只股票一天的事件 = 当天上调家数 - 下调家数（净值 > 0 为升、< 0 为降，净 0 不画）。
逐只拉取较慢（500 只 ≈ 4 分钟），所以接口只读 Redis 缓存；缺失 / 过期的由后台任务补（批量额度、带锁），
响应的 pending_symbols 是还在补的只数。
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import httpx
from redis.asyncio import Redis

from app.cache.operations import acquire_lock, release_lock, set_json
from app.core.logging import logger
from app.schemas.signal_radar import RadarAnalystDayOut, RadarAnalystEventOut, RadarAnalystEventsResponse
from app.services.quant_research.fmp import FmpClient
from app.services.signal_radar import sectors
from app.services.signal_radar.constituents import resolve_constituents
from app.services.signal_radar.universe import get_universe

DEFAULT_DAYS = 10
CACHE_TTL = 24 * 3600          # 缓存最长保留
FRESH_SECONDS = 6 * 3600       # 超过这个时间算过期，后台重拉
REFRESH_LOCK_TTL = 20 * 60
FETCH_CONCURRENCY = 4
GRADES_LIMIT = 200             # 大市值股票一个月就有二三十条变动（含维持），90 天窗口留足余量
MAX_FIRMS = 3
SUPPORTED_MARKETS = {"us"}

_BUY = ("buy", "outperform", "overweight", "positive", "accumulate", "add", "top pick", "long")
_SELL = ("sell", "underperform", "underweight", "reduce", "negative", "short")

_background: set[asyncio.Task] = set()


def bucket_of(grade: str | None) -> str:
    """把券商各家的评级名归成 buy / hold / sell（Neutral / Equal-Weight / Market Perform 等都算 hold）。"""
    g = (grade or "").strip().lower()
    if not g:
        return "hold"
    if any(w in g for w in _SELL):       # 先判卖：「Strong Sell」「Underperform」不能被「perform」类误判
        return "sell"
    if any(w in g for w in _BUY):
        return "buy"
    return "hold"


def parse_actions(raw: object) -> list[dict]:
    """FMP grades 原始行 → 精简动作（日期必须是 YYYY-MM-DD，其余字段缺失按空串）。保持原顺序（新到旧）。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        d = str(r.get("date") or "")[:10]
        try:
            date.fromisoformat(d)
        except ValueError:
            continue
        out.append({"date": d, "firm": str(r.get("gradingCompany") or ""), "prev": str(r.get("previousGrade") or ""),
                    "new": str(r.get("newGrade") or ""), "action": str(r.get("action") or "").lower()})
    return out


def build_events(
    history: dict[str, list[dict]], names: dict[str, str], tags: dict[str, str], since: date,
) -> list[RadarAnalystDayOut]:
    """history: {代码: 动作列表（新到旧）}。每只股票每天净上调 / 下调家数不为 0 即一条事件；日期不早于 since；按日期从新到旧。"""
    by_day: dict[str, list[RadarAnalystEventOut]] = {}
    for symbol, actions in history.items():
        per_day: dict[str, list[dict]] = {}
        for a in actions:
            if a["action"] in ("upgrade", "downgrade") and a["date"] >= since.isoformat():
                per_day.setdefault(a["date"], []).append(a)
        for day, items in per_day.items():
            ups = [a for a in items if a["action"] == "upgrade"]
            downs = [a for a in items if a["action"] == "downgrade"]
            net = len(ups) - len(downs)
            if net == 0:
                continue
            side = ups if net > 0 else downs
            by_day.setdefault(day, []).append(RadarAnalystEventOut(
                symbol=symbol, name=names.get(symbol, symbol), date=day, direction="up" if net > 0 else "down",
                steps=abs(net), upgrades=len(ups), downgrades=len(downs),
                to_bucket=bucket_of(side[-1]["new"]),         # 列表新到旧，最后一条 = 当天最早的一家；取最后一条保持确定
                firms=[a["firm"] for a in side if a["firm"]][:MAX_FIRMS],
                sector=sectors.lookup_tag(tags, symbol)))
    days = []
    for day in sorted(by_day, reverse=True):
        events = sorted(by_day[day], key=lambda e: (-e.steps, e.symbol))
        days.append(RadarAnalystDayOut(
            date=day, up_count=sum(e.direction == "up" for e in events),
            down_count=sum(e.direction == "down" for e in events), events=events))
    return days


def net_counts(actions: list[dict], since: date) -> tuple[int, int]:
    """日期不早于 since 的上调 / 下调家数（维持评级不算）。"""
    since_s = since.isoformat()
    ups = sum(1 for a in actions if a["action"] == "upgrade" and a["date"] >= since_s)
    downs = sum(1 for a in actions if a["action"] == "downgrade" and a["date"] >= since_s)
    return ups, downs


# ---------- 缓存 / 后台拉取 ----------

def cache_key(symbol: str) -> str:
    """单只股票评级变动缓存键。"""
    return f"signal_radar:analyst:v2:{symbol}"


async def _read_cache(redis: Redis, symbols: list[str]) -> dict[str, dict]:
    """一次 MGET 读完所有股票的缓存（逐只 GET 是 N 次往返，标普 500 的好股票上百只）。"""
    if not symbols:
        return {}
    try:
        raws = await redis.mget([cache_key(s) for s in symbols])
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_analyst_cache_read_failed", error=str(e))
        return {}
    out: dict[str, dict] = {}
    for s, raw in zip(symbols, raws, strict=True):
        if raw is None:
            continue
        try:
            v = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(v, dict) and isinstance(v.get("actions"), list):
            out[s] = v
    return out


def _is_stale(entry: dict | None, now: datetime) -> bool:
    if not entry:
        return True
    try:
        at = datetime.fromisoformat(entry["at"])
    except (KeyError, ValueError):
        return True
    return (now - at).total_seconds() > FRESH_SECONDS


async def refresh_symbols(symbols: list[str], redis: Redis) -> int:
    """逐只拉评级变动写缓存（批量额度、并发 4）。返回成功只数。"""
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    done = 0

    async def one(fmp: FmpClient, sym: str) -> None:
        nonlocal done
        async with sem:
            raw = await fmp.get("grades", symbol=sym, limit=GRADES_LIMIT)
        if raw is None:      # 取数失败：不写缓存，下次请求再试
            return
        actions = [a for a in parse_actions(raw) if a["action"] in ("upgrade", "downgrade")]
        await set_json(redis, cache_key(sym), {"at": datetime.now(UTC).isoformat(), "actions": actions},
                       expire=CACHE_TTL)
        done += 1

    async with httpx.AsyncClient() as client:
        fmp = FmpClient(client, redis, "batch")
        await asyncio.gather(*(one(fmp, s) for s in symbols), return_exceptions=True)
    return done


async def refresh_in_background(market: str, universe: str, symbols: list[str], redis: Redis) -> None:
    """后台补拉（带锁，同一 market / universe 范围同时只有一个在跑；失败只记日志）。"""
    lock = f"signal_radar:analyst:refresh:{market}:{universe}"
    if not await acquire_lock(redis, lock, REFRESH_LOCK_TTL):
        return
    try:
        n = await refresh_symbols(symbols, redis)
        logger.info("signal_radar_analyst_refreshed", market=market, universe=universe, requested=len(symbols), ok=n)
    except Exception:
        logger.exception("signal_radar_analyst_refresh_failed", market=market, universe=universe)
    finally:
        await release_lock(redis, lock)


async def cached_with_refresh(
    market: str, scope: str, symbols: list[str], redis: Redis, now: datetime,
) -> dict[str, dict]:
    """读这些股票的评级变动缓存；缺失 / 过期的交给后台补（带锁，scope 区分不同调用方的锁）。返回已有缓存。"""
    cached = await _read_cache(redis, symbols)
    stale = [s for s in symbols if _is_stale(cached.get(s), now)]
    if stale:
        task = asyncio.create_task(refresh_in_background(market, scope, stale, redis))
        _background.add(task)
        task.add_done_callback(_background.discard)
    return cached


async def analyst_events(
    market: str, universe_key: str | None, *, redis: Redis, days: int = DEFAULT_DAYS, now: datetime | None = None,
) -> RadarAnalystEventsResponse | None:
    """None = 不支持的 universe。非美股 supported=False；缓存缺失 / 过期的股票交给后台补，pending_symbols 返回只数。"""
    uni = get_universe(market, universe_key)
    if uni is None:
        return None

    def resp(**kw) -> RadarAnalystEventsResponse:
        return RadarAnalystEventsResponse(market=market, universe_key=uni.key, universe_name=uni.etf_name, **kw)

    if market not in SUPPORTED_MARKETS:
        return resp(supported=False)
    now = now or datetime.now(UTC)
    pairs = await resolve_constituents(market, redis=redis, universe_key=uni.key)
    names = {s: n for s, n in pairs}
    try:
        cached = await cached_with_refresh(market, uni.key, sorted(names), redis, now)
    except Exception:
        logger.exception("signal_radar_analyst_events_read_failed", market=market)
        return resp(available=False)
    tags = await sectors.load_sector_tags(market, redis)
    window = max(1, days)
    history = {s: cached[s]["actions"] for s in names if s in cached}
    missing = sum(1 for s in names if s not in cached)
    return resp(days=build_events(history, names, tags, now.date() - timedelta(days=window)),
                pending_symbols=missing)
