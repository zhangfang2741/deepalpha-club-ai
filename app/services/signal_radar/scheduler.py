"""信号雷达进程内定时预热调度。

在 API 进程存活期间，按各市场收盘时间触发全量扫描并写入 Redis 缓存，让用户进
「信号」Tab 直接命中缓存，而不是首访时触发数十只缠论的慢扫描。用
SIGNAL_RADAR_PREWARM_ENABLED 开关。

不用固定间隔盲扫：同一交易日内日线数据根本不会变，中途重扫白扫算力；只有市场
收盘、数据源把当天日线发布出来之后才有必要重扫。三个市场收盘时间不同（A股/
港股约 UTC 8 点、美股约 UTC 21:30），各自独立算下一次触发时间，谁先到就先扫谁
——这样同一交易日内任意时刻打开雷达，看到的都是当天收盘后那一次扫描算出来的
结果，跟点进详情页当下重新算的结构是一致的（除非数据源本身事后修正历史价格），
不会出现「盲扫间隔正好卡在两次收盘之间」的不必要陈旧窗口。
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.cache.client import current_redis
from app.core.config import settings
from app.core.logging import logger
from app.cache.operations import acquire_lock, release_lock
from app.services.signal_radar.service import (
    SCAN_LOCK_TTL,
    _cache_key,
    compute_demo_day,
    demo_lock_key,
    list_backfill_markers,
    _SESSIONS_UTC,
    compute_market,
    market_session_active,
    refresh_sub_levels,
    scan_lock_key,
)
from app.services.chan.signal_policy import DEFAULT_MODE
from app.services.signal_radar.universe import all_universes


def _modes() -> list[str]:
    """预热 / 盘中次级别刷新覆盖的买卖点口径：默认（宽松）+ 严格。

    新版 App 改用严格口径（雷达、详情页、次级别统一），线上旧版 App 仍请求宽松（默认）口径，
    两套都预热，否则每天第一个打开雷达的人要等一轮全量扫描。默认口径先跑；第二套的日线走
    K 线缓存，不重复拉数，额外开销主要是盘中 30 分钟次级别。旧版用户少了以后可以只留严格口径。
    """
    return [DEFAULT_MODE, "strict"]

# 启动后先等一会儿再首扫，避开启动期其它预热任务抢资源。
_STARTUP_DELAY_SECONDS = 45
# 收盘（窗口末端已含 30 分钟缓冲拿到最后一根K线，见 service._SESSIONS_UTC）后，
# 再等这么久让数据源把当天的日线发布出来，才触发全量重扫——太早去拉可能还是
# 前一天的旧日线。
_POST_CLOSE_BUFFER_MINUTES = 45


async def _prewarm_once(markets: set[str] | None = None) -> None:
    """全量重扫一轮。

    markets 为 None 时覆盖全部目标市场，否则只扫指定市场（按市场收盘触发时用，
    一次只需要扫刚收盘的那个市场）。
    """
    redis = current_redis()
    if redis is None:
        logger.warning("signal_radar_prewarm_no_redis")
        return
    # 串行执行（大盘宽基成分多，避免多套扫描并发抢数据源），按缓存剩余有效期从短到长：
    # 最久没刷新的先扫。进程频繁重启（每次部署）时扫描常被打断，固定按美股→A股→港股的
    # 顺序会让排在后面的市场一直轮不到、停在旧快照上。
    async def remaining_ttl(u) -> int:
        """缓存剩余秒数；没有缓存（-2）或读不到按最旧处理。"""
        try:
            return int(await redis.ttl(_cache_key(u.market, u.key)))
        except Exception:  # noqa: BLE001
            return -2

    targets = _target_universes()
    if markets is not None:
        targets = [u for u in targets if u.market in markets]
    ttls = [await remaining_ttl(u) for u in targets]
    # 稳定排序：剩余 TTL 相同时保持原有顺序
    ordered = [u for _, _, u in sorted(zip(ttls, range(len(targets)), targets, strict=True),
                                       key=lambda x: (x[0], x[1]))]
    for u in ordered:
        for mode in _modes():
            # 与接口触发的扫描共用同一把锁：用户刚好在扫这一份就跳过，不重复扫
            lock = scan_lock_key(u.market, u.key, mode)
            if not await acquire_lock(redis, lock, SCAN_LOCK_TTL):
                logger.info("signal_radar_prewarm_skipped_locked", market=u.market, universe=u.key, mode=mode)
                continue
            try:
                resp = await compute_market(
                    u.market, redis=redis, user_id=None, universe_key=u.key, mode=mode,
                )
                logger.info(
                    "signal_radar_prewarmed", market=u.market, universe=u.key, mode=mode, days=len(resp.days)
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 单个 universe / 口径失败不影响其余
                logger.exception(
                    "signal_radar_prewarm_market_failed", market=u.market, universe=u.key, mode=mode,
                    error=str(e),
                )
            finally:
                await release_lock(redis, lock)


async def _resume_orphan_backfills() -> None:
    """接手上一个进程没补完的补算（部署重启会中断进程内的补算任务）。

    补算标记记在 Redis（service._sync_marker）；owner 不是本进程的即为孤儿。接手方式是
    抢锁重扫这一份（K线多半还在缓存里），扫完仍有失败的由本进程继续后台补算。
    在启动预热之后调用：预热过的那几份已被本进程重写标记，不会重复扫。
    """
    redis = current_redis()
    if redis is None:
        return
    for m in await list_backfill_markers(redis, orphans_only=True):
        kind, market, universe, mode = m.get("kind"), m.get("market"), m.get("universe"), m.get("mode")
        if not (market and universe and mode):
            continue
        lock = demo_lock_key(market, universe, mode) if kind == "demo" else scan_lock_key(market, universe, mode)
        if not await acquire_lock(redis, lock, SCAN_LOCK_TTL):
            continue  # 已有扫描在跑，它会自己处理失败的成分股
        logger.info("signal_radar_backfill_resumed", kind=kind, market=market, universe=universe, mode=mode,
                    pending=len(m.get("pending") or []))
        try:
            if kind == "demo":
                await compute_demo_day(market, universe, redis=redis, mode=mode)
            else:
                await compute_market(market, redis=redis, user_id=None, universe_key=universe, mode=mode)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 单份失败不影响其余
            logger.exception("signal_radar_backfill_resume_failed", kind=kind, market=market,
                             universe=universe, mode=mode, error=str(e))
        finally:
            await release_lock(redis, lock)


def _target_universes() -> list:
    """预热覆盖的 (市场, universe)：与全量预热同一范围。"""
    markets = set(settings.SIGNAL_RADAR_PREWARM_MARKETS)
    return [u for u in all_universes()
            if u.market in markets and (u.is_default or settings.SIGNAL_RADAR_PREWARM_BROAD_ENABLED)]


def _target_markets() -> list[str]:
    """预热覆盖的市场集合（去重，保持 _target_universes 的声明顺序）。"""
    seen: list[str] = []
    for u in _target_universes():
        if u.market not in seen:
            seen.append(u.market)
    return seen


def _next_close_trigger(market: str, after: datetime) -> datetime:
    """该市场下一次「收盘后全量重扫」的触发时间（UTC），从 after 之后找最近一个。

    收盘时间取 service._SESSIONS_UTC 窗口末端，加 _POST_CLOSE_BUFFER_MINUTES 等
    数据源发布当天日线。跳过周末（不识别节假日；节假日触发到了也只是扫一次
    「没有新日线」的空转，无害，容忍度与 market_session_active 一致）。
    """
    window = _SESSIONS_UTC.get(market)
    if window is None:
        raise ValueError(f"unknown market: {market}")
    after = after.astimezone(UTC)
    _, (h2, m2) = window
    candidate = after.replace(hour=h2, minute=m2, second=0, microsecond=0) + timedelta(
        minutes=_POST_CLOSE_BUFFER_MINUTES
    )
    if candidate <= after:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


async def _refresh_sub_levels_once() -> None:
    redis = current_redis()
    if redis is None:
        return
    now = datetime.now(UTC)
    for u in _target_universes():
        if not market_session_active(u.market, now):
            continue
        for mode in _modes():
            try:
                await refresh_sub_levels(u.market, u.key, redis=redis, now=now, mode=mode)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 单个 universe / 口径失败不影响其余
                logger.exception("signal_radar_sub_level_refresh_failed", market=u.market, universe=u.key,
                                 mode=mode, error=str(e))


async def run_signal_radar_sub_level_scheduler() -> None:
    """盘中定时刷新雷达共振标记（次级别结论），直到进程退出。"""
    interval = settings.SIGNAL_RADAR_SUB_LEVEL_REFRESH_SECONDS
    if interval <= 0:
        logger.info("signal_radar_sub_level_refresh_disabled")
        return
    try:
        # 晚于全量首扫启动，首轮通常已有快照可刷
        await asyncio.sleep(_STARTUP_DELAY_SECONDS + interval)
    except asyncio.CancelledError:
        return
    while True:
        try:
            await _refresh_sub_levels_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("signal_radar_sub_level_refresh_loop_failed", error=str(e))
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def run_signal_radar_prewarm_scheduler() -> None:
    """按各市场收盘时间触发全量重扫，直到进程退出。"""
    if not settings.SIGNAL_RADAR_PREWARM_ENABLED:
        logger.info("signal_radar_prewarm_disabled")
        # 不预热也要接手上一个进程没补完的补算，否则重启后那几只就一直缺着
        try:
            await asyncio.sleep(_STARTUP_DELAY_SECONDS)
            await _resume_orphan_backfills()
        except asyncio.CancelledError:
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("signal_radar_backfill_resume_failed", error=str(e))
        return

    try:
        await asyncio.sleep(_STARTUP_DELAY_SECONDS)
    except asyncio.CancelledError:
        return

    markets = _target_markets()
    if not markets:
        return

    # 进程刚起来（部署/重启后）先扫一轮全部市场，保证很快就有缓存可用，不用干等到
    # 下一个收盘触发点——那最长可能要接近 24 小时（如果刚好错过当天的收盘时刻）。
    try:
        await _prewarm_once()
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("signal_radar_prewarm_failed", error=str(e))
    # 预热之后再接手上一个进程没补完的（预热过的那几份已由本进程接管，不会重复扫）
    try:
        await _resume_orphan_backfills()
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("signal_radar_backfill_resume_failed", error=str(e))

    next_trigger = {m: _next_close_trigger(m, datetime.now(UTC)) for m in markets}
    while True:
        market, when = min(next_trigger.items(), key=lambda kv: kv[1])
        wait_seconds = max(0.0, (when - datetime.now(UTC)).total_seconds())
        try:
            await asyncio.sleep(wait_seconds)
        except asyncio.CancelledError:
            return
        try:
            await _prewarm_once(markets={market})
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("signal_radar_prewarm_failed", market=market, error=str(e))
        # 不管这轮扫成功与否都排下一次触发，避免单次失败后这个市场再也不触发。
        next_trigger[market] = _next_close_trigger(market, datetime.now(UTC))
