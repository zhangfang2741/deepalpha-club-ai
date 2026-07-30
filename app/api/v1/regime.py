"""市场状态监控（regime）API 端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import col, select
from starlette.concurrency import run_in_threadpool

from app.api.v1.auth import get_current_user
from app.core.logging import logger
from app.models.regime_features import RegimeFeatures
from app.models.regime_sector_features import RegimeSectorFeatures
from app.models.user import User
from app.schemas.regime import (
    RegimePoint,
    RegimeResponse,
    RegimeStageResult,
    SectorRegimeHistory,
    SectorRegimeLatest,
    SectorRegimePoint,
    SectorStageResult,
)
from app.services.regime.constants import SECTOR_NAME_ZH

router = APIRouter()


def _to_sector_point(row: RegimeSectorFeatures) -> SectorRegimePoint:
    return SectorRegimePoint(
        trade_date=row.trade_date,
        sector=row.sector,
        sector_name=SECTOR_NAME_ZH.get(row.sector, row.sector),
        sector_ret=row.sector_ret,
        sector_vol=row.sector_vol,
        vix=row.vix,
        rs_vs_market=row.rs_vs_market,
        sector_cmf=row.sector_cmf,
        p_risk_on=row.p_risk_on,
        p_neutral=row.p_neutral,
        p_risk_off=row.p_risk_off,
        regime_label=row.regime_label,
        confirmed_label=row.confirmed_label,
        params_version=row.params_version,
        factor_weight=row.factor_weight,
    )


def _to_point(row: RegimeFeatures) -> RegimePoint:
    return RegimePoint(
        trade_date=row.trade_date,
        qqq_return=row.qqq_return,
        realized_vol=row.realized_vol,
        vix=row.vix,
        ods=row.ods,
        cf=row.cf,
        obv_slope=row.obv_slope,
        cmf=row.cmf,
        p_risk_on=row.p_risk_on,
        p_neutral=row.p_neutral,
        p_risk_off=row.p_risk_off,
        regime_label=row.regime_label,
        confirmed_label=row.confirmed_label,
        params_version=row.params_version,
        factor_weight=row.factor_weight,
    )


@router.get("", response_model=RegimeResponse)
async def get_regime(
    limit: int = Query(250, ge=1, le=2000, description="返回最近多少个交易日"),
) -> RegimeResponse:
    """市场状态监控面板数据：最近 N 个交易日的信号/后验/因子权重。"""
    from app.db.session import get_sync_session_cm

    def _load() -> list[RegimeFeatures]:
        with get_sync_session_cm() as session:
            rows = session.exec(
                select(RegimeFeatures)
                .order_by(col(RegimeFeatures.trade_date).desc())
                .limit(limit)
            ).all()
            return list(rows)

    rows = await run_in_threadpool(_load)
    rows.sort(key=lambda r: r.trade_date)  # 升序返回，便于前端画图
    points = [_to_point(r) for r in rows]
    latest = points[-1] if points else None
    logger.info("regime_history_request", limit=limit, returned=len(points))
    return RegimeResponse(latest=latest, history=points)


@router.post("/run", response_model=RegimeStageResult)
async def trigger_regime_stage(
    lookback_days: int = Query(1400, ge=400, le=4000, description="回看日历天数"),
    user: User = Depends(get_current_user),
) -> RegimeStageResult:
    """触发 regime pipeline 阶段：抓数→算状态→落库（因子表）。"""
    from app.db.session import get_sync_session_cm
    from app.services.regime.pipeline import run_regime_stage

    def _run() -> dict:
        with get_sync_session_cm() as session:
            return run_regime_stage(session, lookback_days=lookback_days)

    try:
        summary = await run_in_threadpool(_run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("regime_stage_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"regime 阶段执行失败: {exc}") from exc

    return RegimeStageResult(**summary)


@router.get("/sectors", response_model=SectorRegimeLatest)
async def get_sector_regimes() -> SectorRegimeLatest:
    """各板块最新一日的市场状态（板块状态热力图数据源）。"""
    from app.db.session import get_sync_session_cm

    def _load() -> list[RegimeSectorFeatures]:
        with get_sync_session_cm() as session:
            latest_date = session.exec(
                select(RegimeSectorFeatures.trade_date)
                .order_by(col(RegimeSectorFeatures.trade_date).desc())
                .limit(1)
            ).first()
            if latest_date is None:
                return []
            rows = session.exec(
                select(RegimeSectorFeatures).where(
                    RegimeSectorFeatures.trade_date == latest_date
                )
            ).all()
            return list(rows)

    rows = await run_in_threadpool(_load)
    points = [_to_sector_point(r) for r in rows]
    # 按 factor_weight 降序（越逐利越靠前），None 垫底
    points.sort(key=lambda p: (p.factor_weight is None, -(p.factor_weight or 0)))
    latest_date = points[0].trade_date if points else None
    logger.info("regime_sectors_request", sectors=len(points))
    return SectorRegimeLatest(trade_date=latest_date, sectors=points)


@router.get("/sectors/{sector}", response_model=SectorRegimeHistory)
async def get_sector_history(
    sector: str,
    limit: int = Query(250, ge=1, le=2000),
) -> SectorRegimeHistory:
    """单个板块的历史状态序列。"""
    from app.db.session import get_sync_session_cm

    def _load() -> list[RegimeSectorFeatures]:
        with get_sync_session_cm() as session:
            rows = session.exec(
                select(RegimeSectorFeatures)
                .where(RegimeSectorFeatures.sector == sector)
                .order_by(col(RegimeSectorFeatures.trade_date).desc())
                .limit(limit)
            ).all()
            return list(rows)

    rows = await run_in_threadpool(_load)
    rows.sort(key=lambda r: r.trade_date)
    return SectorRegimeHistory(
        sector=sector,
        sector_name=SECTOR_NAME_ZH.get(sector, sector),
        history=[_to_sector_point(r) for r in rows],
    )


@router.post("/sectors/run", response_model=SectorStageResult)
async def trigger_sector_stage(
    lookback_days: int = Query(1400, ge=400, le=4000),
    user: User = Depends(get_current_user),
) -> SectorStageResult:
    """触发行业级 pipeline 阶段：逐板块算状态→落库。"""
    from app.db.session import get_sync_session_cm
    from app.services.regime.sector_pipeline import run_sector_regime_stage

    def _run() -> dict:
        with get_sync_session_cm() as session:
            return run_sector_regime_stage(session, lookback_days=lookback_days)

    try:
        summary = await run_in_threadpool(_run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("regime_sector_stage_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"板块状态执行失败: {exc}") from exc

    return SectorStageResult(sectors=summary["sectors"], written=summary["written"])
