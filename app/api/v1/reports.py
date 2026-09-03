"""投资报告 API：撰写、发布（打 K 线标记）、报告流、详情（订阅门控）、回测结算。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth.dependencies import get_verified_user_id
from app.core.logging import logger
from app.db.session import get_db
from app.models.analyst import Analyst
from app.models.report import (
    OUTCOME_STATUS_PENDING,
    OUTCOME_STATUS_RESOLVED,
    REPORT_STATUS_DRAFT,
    REPORT_STATUS_PUBLISHED,
    Report,
    ReportOutcome,
)
from app.models.subscription import Subscription
from app.schemas.astock import KlineBar
from app.schemas.report import (
    EvaluateResponse,
    OutcomeOut,
    PublishResponse,
    ReportCreate,
    ReportDetail,
    ReportListItem,
    ReportListResponse,
    ReportUpdate,
)
from app.services.astock.client import (
    AStockDataUnavailable,
    fetch_close_on_or_after,
    fetch_daily_bars,
)
from app.services.astock.symbols import InvalidSymbolError, normalize_symbol
from app.services.reports.accuracy import evaluate_direction, horizon_end_date
from app.services.reports.access import SubscriptionView, can_view_content
from app.utils.auth import verify_token

router = APIRouter()

_optional_security = HTTPBearer(auto_error=False)


async def get_optional_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_security),
) -> Optional[int]:
    """可选认证：有合法 token 返回 user_id，否则 None（不报错，供公开端点用）。"""
    if credentials is None:
        return None
    user_id = verify_token(credentials.credentials)
    if user_id is None:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


async def _require_analyst(db: AsyncSession, user_id: int) -> Analyst:
    """取当前账号的经纪人档案，未建档则 403。"""
    analyst = (
        await db.execute(select(Analyst).where(Analyst.user_id == user_id))
    ).scalar_one_or_none()
    if analyst is None:
        raise HTTPException(status_code=403, detail="仅经纪人可执行此操作，请先成为经纪人")
    return analyst


async def _get_report_or_404(db: AsyncSession, report_id: UUID) -> Report:
    report = (
        await db.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


async def _get_outcome(db: AsyncSession, report_id: UUID) -> Optional[ReportOutcome]:
    return (
        await db.execute(
            select(ReportOutcome).where(ReportOutcome.report_id == report_id)
        )
    ).scalar_one_or_none()


async def _load_subscription_views(
    db: AsyncSession, user_id: int
) -> list[SubscriptionView]:
    subs = (
        await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    ).scalars().all()
    return [
        SubscriptionView(
            tier=s.tier, analyst_id=s.analyst_id, status=s.status, end_at=s.end_at
        )
        for s in subs
    ]


# ---------------------------------------------------------------------------
# 撰写 / 更新草稿
# ---------------------------------------------------------------------------


@router.post("/", response_model=ReportListItem, status_code=201)
async def create_report(
    payload: ReportCreate,
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> ReportListItem:
    """撰写报告（草稿，未打标记）。"""
    try:
        payload.validate_semantics()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        symbol = normalize_symbol(payload.symbol)
    except InvalidSymbolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    analyst = await _require_analyst(db, user_id)
    report = Report(
        analyst_id=analyst.id,
        symbol=symbol,
        title=payload.title,
        summary=payload.summary,
        content=payload.content,
        direction=payload.direction,
        horizon_days=payload.horizon_days,
        target_price=payload.target_price,
        visibility=payload.visibility,
        status=REPORT_STATUS_DRAFT,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    logger.info("report_created", report_id=str(report.id), analyst_id=str(analyst.id))
    return ReportListItem.model_validate(report)


@router.patch("/{report_id}", response_model=ReportListItem)
async def update_report(
    report_id: UUID,
    payload: ReportUpdate,
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> ReportListItem:
    """更新草稿（已发布报告不可再改）。"""
    analyst = await _require_analyst(db, user_id)
    report = await _get_report_or_404(db, report_id)
    if report.analyst_id != analyst.id:
        raise HTTPException(status_code=403, detail="只能修改自己的报告")
    if report.status == REPORT_STATUS_PUBLISHED:
        raise HTTPException(status_code=409, detail="报告已发布，不可修改")

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(report, key, value)
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return ReportListItem.model_validate(report)


# ---------------------------------------------------------------------------
# 发布：打 K 线标记
# ---------------------------------------------------------------------------


@router.post("/{report_id}/publish", response_model=PublishResponse)
async def publish_report(
    report_id: UUID,
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> PublishResponse:
    """发布报告：记录发布当时收盘价与交易日作为 K 线标记，并建立待结算回测。"""
    analyst = await _require_analyst(db, user_id)
    report = await _get_report_or_404(db, report_id)
    if report.analyst_id != analyst.id:
        raise HTTPException(status_code=403, detail="只能发布自己的报告")
    if report.status == REPORT_STATUS_PUBLISHED:
        raise HTTPException(status_code=409, detail="报告已发布")

    # 取最近若干交易日 K 线，末根即「发布当时」的收盘价与交易日
    today = datetime.now(UTC).date()
    start = (today - timedelta(days=15)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    try:
        bars = await fetch_daily_bars(report.symbol, start, end)
    except AStockDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"无法获取行情打标记：{exc}") from exc
    if not bars:
        raise HTTPException(status_code=503, detail="未获取到该标的近期 K 线，无法打标记")

    last = bars[-1]
    report.mark_price = last["close"]
    report.mark_date = last["date"]
    report.status = REPORT_STATUS_PUBLISHED
    report.published_at = datetime.now(UTC)
    db.add(report)

    # 建立待结算回测
    end_date = horizon_end_date(report.mark_date, report.horizon_days)
    outcome = await _get_outcome(db, report.id)
    if outcome is None:
        outcome = ReportOutcome(
            report_id=report.id,
            status=OUTCOME_STATUS_PENDING,
            horizon_end_date=end_date,
        )
        db.add(outcome)
    else:
        outcome.horizon_end_date = end_date
        outcome.status = OUTCOME_STATUS_PENDING
        db.add(outcome)

    await db.commit()
    await db.refresh(report)
    await db.refresh(outcome)
    logger.info(
        "report_published",
        report_id=str(report.id),
        mark_price=report.mark_price,
        mark_date=report.mark_date,
    )
    return PublishResponse(
        id=report.id,
        status=report.status,
        mark_price=report.mark_price,
        mark_date=report.mark_date,
        published_at=report.published_at,
        outcome=OutcomeOut.model_validate(outcome),
    )


# ---------------------------------------------------------------------------
# 回测结算
# ---------------------------------------------------------------------------


@router.post("/{report_id}/evaluate", response_model=EvaluateResponse)
async def evaluate_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EvaluateResponse:
    """结算一篇已发布报告的回测（到期后取到期日收盘价，判定命中）。

    未到期或到期日尚无行情时保持 PENDING。
    """
    report = await _get_report_or_404(db, report_id)
    if report.status != REPORT_STATUS_PUBLISHED or report.mark_price is None or report.mark_date is None:
        raise HTTPException(status_code=409, detail="报告未发布或缺少标记，无法结算")

    outcome = await _get_outcome(db, report.id)
    if outcome is None:
        outcome = ReportOutcome(
            report_id=report.id,
            status=OUTCOME_STATUS_PENDING,
            horizon_end_date=horizon_end_date(report.mark_date, report.horizon_days),
        )
        db.add(outcome)

    if outcome.status == OUTCOME_STATUS_RESOLVED:
        return EvaluateResponse(
            id=report.id, outcome=OutcomeOut.model_validate(outcome), message="已结算"
        )

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if outcome.horizon_end_date > today:
        await db.commit()
        await db.refresh(outcome)
        return EvaluateResponse(
            id=report.id,
            outcome=OutcomeOut.model_validate(outcome),
            message="尚未到期",
        )

    try:
        bar = await fetch_close_on_or_after(report.symbol, outcome.horizon_end_date)
    except AStockDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if bar is None:
        await db.commit()
        await db.refresh(outcome)
        return EvaluateResponse(
            id=report.id,
            outcome=OutcomeOut.model_validate(outcome),
            message="到期日暂无行情，稍后重试",
        )

    return_pct, hit = evaluate_direction(
        report.direction, report.mark_price, bar["close"]
    )
    outcome.price_at_horizon = bar["close"]
    outcome.actual_return_pct = return_pct
    outcome.is_correct = hit
    outcome.status = OUTCOME_STATUS_RESOLVED
    outcome.resolved_at = datetime.now(UTC)
    db.add(outcome)
    await db.commit()
    await db.refresh(outcome)
    logger.info(
        "report_evaluated",
        report_id=str(report.id),
        return_pct=return_pct,
        is_correct=hit,
    )
    return EvaluateResponse(
        id=report.id, outcome=OutcomeOut.model_validate(outcome), message="已结算"
    )


# ---------------------------------------------------------------------------
# 报告流 / 详情（订阅门控）
# ---------------------------------------------------------------------------


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    analyst_id: Optional[UUID] = Query(None, description="按经纪人过滤"),
    symbol: Optional[str] = Query(None, description="按标的过滤"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    """报告流（仅摘要，始终公开；正文在详情页做门控）。只列已发布报告。"""
    conds = [Report.status == REPORT_STATUS_PUBLISHED]
    if analyst_id is not None:
        conds.append(Report.analyst_id == analyst_id)
    if symbol is not None:
        try:
            conds.append(Report.symbol == normalize_symbol(symbol))
        except InvalidSymbolError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    total = (
        await db.execute(select(func.count()).select_from(Report).where(*conds))
    ).scalar_one()
    stmt = (
        select(Report)
        .where(*conds)
        .order_by(Report.published_at.desc())
        .limit(limit)
        .offset(offset)
    )
    reports = (await db.execute(stmt)).scalars().all()

    items: list[ReportListItem] = []
    for report in reports:
        item = ReportListItem.model_validate(report)
        outcome = await _get_outcome(db, report.id)
        if outcome is not None:
            item.outcome = OutcomeOut.model_validate(outcome)
        items.append(item)
    return ReportListResponse(items=items, total=int(total))


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: UUID,
    with_bars: bool = Query(True, description="是否附带标记点前后 K 线"),
    viewer_user_id: Optional[int] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> ReportDetail:
    """报告详情：标记点 + 后续 K 线 + 回测结论 + 门控正文。"""
    report = await _get_report_or_404(db, report_id)
    analyst = (
        await db.execute(select(Analyst).where(Analyst.id == report.analyst_id))
    ).scalar_one_or_none()
    if analyst is None:
        raise HTTPException(status_code=404, detail="报告作者不存在")

    subs = (
        await _load_subscription_views(db, viewer_user_id)
        if viewer_user_id is not None
        else []
    )
    allowed = can_view_content(
        viewer_user_id=viewer_user_id,
        report_analyst_user_id=analyst.user_id,
        report_analyst_id=analyst.id,
        report_visibility=report.visibility,
        subscriptions=subs,
    )

    detail = ReportDetail(
        id=report.id,
        analyst_id=report.analyst_id,
        symbol=report.symbol,
        symbol_name=report.symbol_name,
        title=report.title,
        summary=report.summary,
        content=report.content if allowed else "",
        direction=report.direction,
        horizon_days=report.horizon_days,
        target_price=report.target_price,
        status=report.status,
        visibility=report.visibility,
        mark_price=report.mark_price,
        mark_date=report.mark_date,
        published_at=report.published_at,
        created_at=report.created_at,
        locked=not allowed,
    )

    outcome = await _get_outcome(db, report.id)
    if outcome is not None:
        detail.outcome = OutcomeOut.model_validate(outcome)

    # 附带 K 线：标记点前 60 日到 时限之后一段（展示后续走势）
    if with_bars and report.mark_date:
        base = datetime.strptime(report.mark_date, "%Y-%m-%d")
        start = (base - timedelta(days=90)).strftime("%Y-%m-%d")
        end = (base + timedelta(days=report.horizon_days + 30)).strftime("%Y-%m-%d")
        try:
            bars = await fetch_daily_bars(report.symbol, start, end)
            detail.bars = [KlineBar(**b) for b in bars]
        except AStockDataUnavailable:
            logger.warning("report_detail_bars_unavailable", report_id=str(report.id))
            detail.bars = []

    return detail
