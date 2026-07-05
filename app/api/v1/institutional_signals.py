"""机构资金信号 API 端点。"""
import asyncio
import hashlib
import inspect
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis

from app.cache.client import current_redis, get_redis_optional
from app.core.logging import logger
from app.db.session import AsyncSessionFactory
from app.schemas import institutional_signals as _signals_schema
from app.schemas.institutional_signals import (
    InstitutionalSignalReport,
    LeaderboardResponse,
)
from app.services.institutional_signals import calculator as _calc
from app.services.institutional_signals import compute_institutional_signals
from app.services.institutional_signals import constants as _const
from app.services.institutional_signals import deltas as _deltas
from app.services.institutional_signals import dimensions as _dims
from app.services.institutional_signals import fetchers as _fetchers
from app.services.institutional_signals import scan as _scan
from app.services.institutional_signals import states as _states
from app.services.institutional_signals.constants import SCAN_FRESH_SECONDS
from app.services.institutional_signals.scan import scan_leaderboard


def _auto_cache_version() -> str:
    """由影响输出的源码模块自动算哈希——任一改动即使缓存失效，无需手动升版本。

    读不到源码（如纯 .pyc 运行）时回退到固定串，宁可不自动失效也不崩。
    """
    mods = [_dims, _states, _calc, _scan, _const, _fetchers, _deltas, _signals_schema]
    h = hashlib.md5()
    for m in mods:
        try:
            h.update(inspect.getsource(m).encode("utf-8"))
        except (OSError, TypeError):
            h.update(m.__name__.encode("utf-8"))
    return h.hexdigest()[:10]


router = APIRouter()

CACHE_PREFIX = "institutional_signals"
CACHE_TTL = 3600  # 1 小时
# 缓存版本 = 相关源码哈希：状态名/schema/打分/端点任一变更，缓存 key 自动变、旧缓存立即失效
SIGNALS_CACHE_VERSION = _auto_cache_version()
REPORT_CACHE_VERSION = SIGNALS_CACHE_VERSION

# 榜单缓存：stale-while-revalidate（按 universe 分键）
LB_UNIVERSES = ("sp500", "nasdaq100")
LB_DATA_TTL = 86400   # 数据保留 24h（过期前一直可作为 stale 返回）
LB_LOCK_TTL = 900     # 扫描锁 15min，防并发重复扫描
LB_CACHE_VERSION = SIGNALS_CACHE_VERSION


def _lb_keys(universe: str) -> tuple[str, str, str]:
    """返回某 universe 的 (数据键, 新鲜标记键, 扫描锁键)。"""
    base = f"institutional_signals:leaderboard:{universe}:{LB_CACHE_VERSION}"
    return base, f"{base}:fresh", f"{base}:lock"

# 保持对后台任务的强引用，避免被 GC 回收
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _refresh_leaderboard(universe: str) -> None:
    """后台扫描指定 universe 并写缓存；用锁避免并发重复扫描。"""
    data_key, fresh_key, lock_key = _lb_keys(universe)
    redis = current_redis()
    if redis is not None:
        try:
            got = await redis.set(lock_key, b"1", nx=True, ex=LB_LOCK_TTL)
            if not got:
                return  # 已有扫描在进行
        except Exception as e:
            logger.warning("leaderboard_lock_failed", universe=universe, error=str(e))
    try:
        result = await scan_leaderboard(universe=universe)
        if redis is not None:
            await redis.set(data_key, result.model_dump_json(), ex=LB_DATA_TTL)
            await redis.set(fresh_key, b"1", ex=SCAN_FRESH_SECONDS)
        logger.info("leaderboard_refreshed", universe=universe, scanned=result.scanned)
    except Exception:
        logger.exception("leaderboard_refresh_failed", universe=universe)
    finally:
        if redis is not None:
            try:
                await redis.delete(lock_key)
            except Exception:
                pass


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    universe: str = Query("sp500", description="universe：sp500（标普500）| nasdaq100（纳指100/QQQ）"),
    refresh: bool = Query(False, description="true 时清空该 universe 缓存并强制后台重扫"),
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> LeaderboardResponse:
    """机构建仓榜：扫描动态 universe（标普 500 或纳指 100），按综合分与偏多状态排名。

    基于 4 个 FMP 维度（不含期权仓位），点进详情页查看完整五维。
    stale-while-revalidate：命中缓存立即返回；过期则先返回旧数据再后台刷新；
    无缓存则后台开扫并返回 computing，前端稍后重试。
    refresh=true：手动清空该 universe 的数据/新鲜标记/扫描锁，强制重扫（用于残缺快照补救）。
    """
    if universe not in LB_UNIVERSES:
        raise HTTPException(status_code=422, detail=f"universe 仅支持 {LB_UNIVERSES}")

    if redis is None:
        # 无缓存无法后台化，返回 computing 提示（详情页查询不受影响）
        return LeaderboardResponse(status="computing", note="缓存不可用，榜单暂不可用")

    data_key, fresh_key, lock_key = _lb_keys(universe)

    if refresh:
        # 清空旧快照 + 锁，确保下面能重新拿到锁并开扫（否则残缺快照会赖到 TTL 过期）
        try:
            await redis.delete(data_key, fresh_key, lock_key)
        except Exception as e:
            logger.warning("leaderboard_refresh_clear_failed", universe=universe, error=str(e))
        _spawn(_refresh_leaderboard(universe))
        logger.info("leaderboard_manual_refresh", universe=universe)
        return LeaderboardResponse(status="computing", note="已清空缓存，正在后台重扫，请稍后刷新")

    try:
        cached = await redis.get(data_key)
        fresh = await redis.exists(fresh_key)
    except Exception as e:
        logger.warning("leaderboard_cache_read_failed", universe=universe, error=str(e))
        cached, fresh = None, False

    if cached:
        if not fresh:
            _spawn(_refresh_leaderboard(universe))  # 过期：后台刷新，本次先返回旧数据
        return LeaderboardResponse.model_validate_json(cached)

    _spawn(_refresh_leaderboard(universe))
    return LeaderboardResponse(status="computing", note="正在后台扫描 universe，请稍后刷新")


@router.get("", response_model=InstitutionalSignalReport)
async def get_institutional_signals(
    symbol: str = Query(..., min_length=1, max_length=10, description="股票代码，如 AAPL"),
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> InstitutionalSignalReport:
    """获取单支标的的机构资金信号报告（五维评分 + 状态标签）。

    维度：Expectation（预期）/ Positioning（仓位）/ Participation（参与度）/
    Fundamental（基本面）/ Confirmation（确认）。当前 Phase 1 覆盖预期与参与度。
    结果缓存 1 小时；Redis 不可用时降级实时计算。
    """
    symbol = symbol.upper().strip()
    if not symbol.isalpha():
        raise HTTPException(status_code=422, detail="股票代码仅允许字母")

    cache_key = f"{CACHE_PREFIX}:{symbol}:{REPORT_CACHE_VERSION}"

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                logger.info("institutional_signals_cache_hit", symbol=symbol)
                return InstitutionalSignalReport.model_validate_json(cached)
        except Exception as e:
            logger.warning("institutional_signals_cache_read_failed", symbol=symbol, error=str(e))

    logger.info("institutional_signals_cache_miss", symbol=symbol)
    # 每日快照写入 + 变化率信号（best-effort：DB 不可用不影响报告）
    session = AsyncSessionFactory()
    try:
        report = await compute_institutional_signals(symbol, session=session)
    finally:
        await session.close()

    if redis is not None:
        try:
            await redis.set(cache_key, report.model_dump_json(), ex=CACHE_TTL)
        except Exception as e:
            logger.warning("institutional_signals_cache_write_failed", symbol=symbol, error=str(e))

    return report
