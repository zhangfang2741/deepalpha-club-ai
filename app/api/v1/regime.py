"""市场状态监控（regime）API 端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import col, select
from starlette.concurrency import run_in_threadpool

from app.api.v1.auth import get_current_user
from app.core.logging import logger
from app.models.regime_features import RegimeFeatures
from app.models.user import User
from app.schemas.regime import RegimePoint, RegimeResponse, RegimeStageResult

router = APIRouter()


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
