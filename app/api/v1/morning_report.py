"""晨报路由：获取当日/历史、日期列表、APNs token 注册（登录即可免费）。"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.auth.dependencies import get_current_user
from app.core.logging import logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.morning_report import (
    AckResponse,
    DeviceTokenRequest,
    MorningReportResponse,
    ReportDatesResponse,
    ReportMeta,
)
from app.services.morning_report import store
from app.services.morning_report.schema import MorningReportContent

router = APIRouter()


@router.get("", response_model=MorningReportResponse)
async def get_morning_report(
    market: str = Query(pattern="^(us|cn|hk)$"),
    report_date: date | None = Query(None, description="YYYY-MM-DD，不传取当日"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MorningReportResponse:
    """获取指定市场的晨报：不传日期取当日，无当日成功版则回退最近一期。"""
    logger.info("morning_report_request", market=market, date=report_date, user_id=user.id)
    record, stale = await store.get_report(db, market, report_date)
    if record is None:
        return MorningReportResponse(
            meta=ReportMeta(market=market, trade_date=report_date, status="pending", stale=False)
        )
    content = MorningReportContent.model_validate(record.content) if record.content else None
    return MorningReportResponse(
        meta=ReportMeta(market=market, trade_date=record.trade_date, status=record.status, stale=stale),
        content=content,
    )


@router.get("/dates", response_model=ReportDatesResponse)
async def list_morning_report_dates(
    market: str = Query(pattern="^(us|cn|hk)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportDatesResponse:
    """列出指定市场已生成成功的晨报日期（供历史页选择）。"""
    return ReportDatesResponse(market=market, dates=await store.list_dates(db, market))


@router.post("/device-token", response_model=AckResponse)
async def register_device_token(
    body: DeviceTokenRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AckResponse:
    """注册/更新当前用户的 APNs 设备 token，用于晨报推送。"""
    logger.info("device_token_registered", user_id=user.id, locale=body.locale)
    await store.upsert_token(db, user.id, body.token, body.locale)
    return AckResponse()
