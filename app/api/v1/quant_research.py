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
from app.services.quant_research.builder import METHODOLOGY_VERSION
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


@router.get("/diagnostics")
@limiter.limit("6 per minute")
async def quant_diagnostics(request: Request, market: Literal["us", "cn", "hk"] = Query("us")) -> dict:
    """评分方法上线诊断：最新一天与上一方法版本的**汇总**对比（等级分布 / 阶段 / 升降 / 并列占比）。

    只读、不需要登录、**只返回汇总统计，不含任何个股代码或明细**（分组少于 10 只不给均值）。
    临时工具：方法稳定后删除本接口与 services/quant_research/diagnostics.py。
    """
    from app.services.quant_research import diagnostics as diag
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates(market)
    if not dates:
        return {"status": "no_data"}
    new_day, new_ver, _ = dates[0]
    old_day = next((d for d in dates[1:] if d[1] != new_ver), None)
    new_rows = await repo.diagnostic_rows(market, new_day)
    out: dict = {
        "status": "ok", "market": market, "current_methodology": METHODOLOGY_VERSION,
        "days": [{"as_of": d.isoformat(), "version": v, "rows": n} for d, v, n in dates],
        "new": {"as_of": new_day.isoformat(), **diag.summarize(new_rows)},
    }
    if old_day is not None:
        old_rows = await repo.diagnostic_rows(market, old_day[0])
        out["old"] = {"as_of": old_day[0].isoformat(), **diag.summarize(old_rows)}
        out["compare"] = diag.compare(old_rows, new_rows)
    out["ties"] = diag.tie_stats(await repo.get_distributions(market, new_day))
    return out


@router.get("/diagnostics/scan")
@limiter.limit("6 per minute")
async def quant_diagnostics_scan(request: Request, market: Literal["us", "cn", "hk"] = Query("us")) -> dict:
    """全景扫描：从最新一天的板块分布看每个指标有没有异常（覆盖不足 / 并列严重 / 极值离谱 / 板块缺失）。

    只读一次分布表（已落库的聚合数据），不读个股、不请求任何数据源，对线上基本无负担；只返回指标统计，不含个股。
    临时工具：与 /diagnostics 一起在方法稳定后删除。
    """
    from app.services.quant_research import diagnostics as diag
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates(market)
    if not dates:
        return {"status": "no_data"}
    day, version, _ = dates[0]
    scan = diag.scan_distributions(await repo.get_distributions(market, day))
    return {"status": "ok", "market": market, "as_of": day.isoformat(), "version": version, **scan}


@router.get("/diagnostics/whatif")
@limiter.limit("6 per minute")
async def quant_diagnostics_whatif(request: Request, market: Literal["us", "cn", "hk"] = Query("us")) -> dict:
    """反事实：用最新一天已存的综合分，比较「综合分和谁比」三种口径（全体 / 所有阶段同阶段比 / 只有成长·成熟·无阶段同阶段比）下各阶段的等级分布。

    只读已落库结果，不读数据源、不写库；只返回各阶段汇总。临时工具，与 /diagnostics 一起在方法稳定后删除。
    """
    from app.services.quant_research import diagnostics as diag
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates(market)
    if not dates:
        return {"status": "no_data"}
    day, version, _ = dates[0]
    return {"status": "ok", "market": market, "as_of": day.isoformat(), "version": version,
            **diag.whatif_cohort(await repo.diagnostic_rows(market, day))}


@router.get("/diagnostics/netgap")
@limiter.limit("2 per minute")
async def quant_diagnostics_netgap(request: Request, market: Literal["us", "cn", "hk"] = Query("us")) -> dict:
    """净利率 vs EBIT 利润率的差距分布（一次性收益对净利润口径指标的影响面）。

    分页读已落库结果里的两个指标值（每页之间让出时间），不请求任何数据源；只返回占比 / 分位，不含个股。
    临时工具，与 /diagnostics 一起在方法稳定后删除。
    """
    from app.services.quant_research import diagnostics as diag
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates(market)
    if not dates:
        return {"status": "no_data"}
    day, version, _ = dates[0]
    values = await repo.metric_values(market, day, ("net_m", "ebit_m"))
    return {"status": "ok", "market": market, "as_of": day.isoformat(), "version": version, **diag.net_margin_gap(values)}


@router.get("/diagnostics/sbcwhatif")
@limiter.limit("2 per minute")
async def quant_diagnostics_sbcwhatif(request: Request, market: Literal["us", "cn", "hk"] = Query("us")) -> dict:
    """反事实：盈利能力新增「加回股权激励的经营利润率」会改变谁（影响面测算，不改评分）。

    分页读已落库结果（页间让出时间），不请求任何数据源；只返回聚合，不含个股。临时工具，与 /diagnostics 一起在方法稳定后删除。
    """
    from app.services.quant_research import diagnostics as diag
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates(market)
    if not dates:
        return {"status": "no_data"}
    day, version, _ = dates[0]
    return {"status": "ok", "market": market, "as_of": day.isoformat(), "version": version,
            **diag.sbc_adjust_whatif(await repo.sbc_rows(market, day))}


@router.get("/diagnostics/nongaap")
@limiter.limit("1 per minute")
async def quant_diagnostics_nongaap(request: Request, market: Literal["us"] = Query("us"),
                                    n: int = Query(60, ge=20, le=100)) -> dict:
    """抽样核查 FMP 非 GAAP 实际 EPS：覆盖率（≥4 / ≥8 个季度）与和 GAAP EPS 的差距分档。

    每只抽样股票 2 次 FMP 调用（走全局预算、批量优先级），只返回聚合，不含个股代码。临时工具，与 /diagnostics 一起在方法稳定后删除。
    """
    from app.services.quant_research import diagnostics as diag
    from app.services.quant_research import nongaap_probe
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates(market)
    if not dates:
        return {"status": "no_data"}
    day, version, _ = dates[0]
    sample = await repo.symbol_sample(market, day, n)
    rows = await nongaap_probe.probe(sample, day, current_redis())
    return {"status": "ok", "market": market, "as_of": day.isoformat(), "version": version, **diag.nongaap_summary(rows)}


@router.get("/diagnostics/nongaap-whatif")
@limiter.limit("6 per minute")
async def quant_diagnostics_nongaap_whatif(request: Request, restart: bool = Query(False)) -> dict:
    """美股改用非 GAAP 实际 EPS（市盈率 / EPS 同比 / PEG）的等级反事实：后台任务，接口只触发 / 查询进度，结果放进程内存。

    全体约 1500 次 FMP 调用（走全局预算、批量优先级）。restart=true 丢弃上次结果重跑。只返回聚合，不含个股。临时工具，随 /diagnostics 一起删除。
    """
    from app.services.quant_research import nongaap_job
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates("us")
    if not dates:
        return {"status": "no_data"}
    if restart:
        nongaap_job.reset()
    return await nongaap_job.start("us", dates[0][0], current_redis())


@router.get("/diagnostics/panorama")
@limiter.limit("2 per minute")
async def quant_diagnostics_panorama(request: Request, market: Literal["us", "cn", "hk"] = Query("us")) -> dict:
    """维度与指标统计体检：维度间相关、名义占比 vs 有效影响、板块偏差、指标状态 / 百分位分布、同维度冗余指标对。

    分页读已落库结果（页间让出时间），不请求任何数据源；只返回聚合统计，不含个股代码。临时工具，方法稳定后删除。
    """
    from app.services.quant_research import diagnostics as diag
    from app.services.quant_research import repository as repo

    dates = await repo.diagnostic_dates(market)
    if not dates:
        return {"status": "no_data"}
    day, version, _ = dates[0]
    return {"status": "ok", "market": market, "as_of": day.isoformat(), "version": version,
            **diag.panorama(await repo.panorama_rows(market, day))}


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
