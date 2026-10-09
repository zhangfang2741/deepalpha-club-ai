"""量化研究接口：个股六维度量化研究 + 方法说明。业务逻辑见 app/services/quant_research。"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Path, Query, Request
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import current_redis, get_redis_optional
from app.cache.operations import acquire_lock, release_lock
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.quant_research import LatestReportOut, MethodologyOut, QuantResearchOut, ReportSummaryOut
from app.core.config import settings
from app.services.quant_research.batch import run_us_batch
from app.services.quant_research.cnhk.batch import run_cn_batch, run_hk_batch
from app.services.quant_research.methodology import build_methodology
from app.services.quant_research.report import get_latest_report
from app.services.quant_research.report_summary import get_report_summary
from app.services.quant_research.scheduler import _LOCK_TTL, _lock_key, last_cnhk_session, last_us_session
from app.services.quant_research.service import get_quant_research

router = APIRouter()

_background_tasks: set[asyncio.Task] = set()


@router.get("/methodology", response_model=MethodologyOut)
async def quant_methodology(lang: Literal["zh", "en"] = Query("zh")) -> MethodologyOut:
    """方法说明（「等级是怎么算的？」）。"""
    return build_methodology(lang)


@router.post("/batch/run")
@limiter.limit("3 per minute")
async def quant_batch_run(
    request: Request,
    market: Literal["us", "cn", "hk"] = Query("us"),
    user: User = Depends(get_current_user),
) -> dict:
    """手动触发批量（美股标普1500 / A 股市值前 1800 / 港股样本全量），口径切换 / 补数时不用等夜间定时。

    与定时批量、自举共用同一把 Redis 锁：同一天只跑一轮；正在跑时返回 already_running。
    后台执行不阻塞响应，结果照常写入 quant_results / 板块分布。
    """
    now = datetime.now(UTC)
    day = last_us_session(now) if market == "us" else last_cnhk_session(now, _CLOSE_HOUR[market]())
    redis = current_redis()
    if redis is not None and not await acquire_lock(redis, _lock_key(market, day), _LOCK_TTL):
        logger.info("quant_batch_manual_skipped_locked", market=market, day=day.isoformat(), user_id=user.id)
        return {"status": "already_running", "market": market, "day": day.isoformat()}
    logger.info("quant_batch_manual_started", market=market, day=day.isoformat(), user_id=user.id)
    task = asyncio.create_task(_run_manual_batch(market, day))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "started", "market": market, "day": day.isoformat()}


_CLOSE_HOUR = {"cn": lambda: settings.QUANT_CN_BATCH_UTC_HOUR, "hk": lambda: settings.QUANT_HK_BATCH_UTC_HOUR}


async def _run_manual_batch(market: str, day: date) -> None:
    """后台跑完手动批量；无论成败都释放锁，失败不挡当晚定时批（定时点重抢）。"""
    redis = current_redis()
    try:
        if market == "us":
            async with httpx.AsyncClient() as client:
                summary = await run_us_batch(day, redis=redis, client=client)
        elif market == "cn":
            summary = await run_cn_batch(day, redis=redis)
        else:
            summary = await run_hk_batch(day, redis=redis)
        logger.info("quant_batch_manual_finished", market=market, day=day.isoformat(), summary=summary)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("quant_batch_manual_failed", market=market, day=day.isoformat())
    finally:
        if redis is not None:
            await release_lock(redis, _lock_key(market, day))


@router.get("/{market}/{symbol}/report", response_model=LatestReportOut)
@limiter.limit("30 per minute")
async def latest_report(
    request: Request,
    market: str = Path(..., pattern=r"^[a-zA-Z]{2}$"),
    symbol: str = Path(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9\-\.]{0,11}$"),
    lang: Literal["zh", "en"] = Query("zh"),
    kind: Literal["latest", "annual"] = Query("latest", description="latest = 最新一份定期报告；annual = 最新年报"),
    user: User = Depends(get_current_user),
    redis: Redis | None = Depends(get_redis_optional),
) -> LatestReportOut:
    """最新一份定期财报（年报 / 中报 / 季报）原文的位置；文件由 App 下载并缓存在本机。"""
    out = await get_latest_report(market.lower(), symbol, lang, redis=redis, kind=kind)
    logger.info("latest_report_served", market=market, symbol=symbol.upper(), status=out.status, user_id=user.id)
    return out


@router.get("/{market}/{symbol}/report/summary", response_model=ReportSummaryOut)
@limiter.limit("30 per minute")
async def latest_report_summary(
    request: Request,
    market: str = Path(..., pattern=r"^[a-zA-Z]{2}$"),
    symbol: str = Path(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9\-\.]{0,11}$"),
    lang: Literal["zh", "en"] = Query("zh"),
    kind: Literal["latest", "annual"] = Query("latest"),
    peek: bool = Query(False, description="只看缓存，不触发生成"),
    user: User = Depends(get_current_user),
    redis: Redis | None = Depends(get_redis_optional),
) -> ReportSummaryOut:
    """最新财报的中文要点。没有缓存时会触发后台生成并返回 generating，客户端隔几秒再请求。"""
    out = await get_report_summary(market.lower(), symbol, lang, redis=redis, kind=kind, generate=not peek)
    logger.info("report_summary_served", market=market, symbol=symbol.upper(), status=out.status, user_id=user.id)
    return out


@router.get("/{market}/{symbol}", response_model=QuantResearchOut)
@limiter.limit("20 per minute")
async def quant_research(
    request: Request,
    market: str = Path(..., pattern=r"^[a-zA-Z]{2}$"),
    symbol: str = Path(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9\-\.]{0,11}$"),
    lang: Literal["zh", "en"] = Query("zh"),
    user: User = Depends(get_current_user),
    redis: Redis | None = Depends(get_redis_optional),
) -> QuantResearchOut:
    """个股量化研究（六维度、三层下钻所需的全部数据）。"""
    out = await get_quant_research(market, symbol, lang, redis=redis)
    logger.info("quant_research_served", market=market, symbol=symbol.upper(), status=out.status, user_id=user.id)
    return out
