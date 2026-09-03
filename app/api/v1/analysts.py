"""经纪人（分析师）API：建档、列表、主页、准确率榜单。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth.dependencies import get_verified_user_id
from app.core.logging import logger
from app.db.session import get_db
from app.models.analyst import Analyst
from app.models.report import (
    REPORT_STATUS_PUBLISHED,
    Report,
    ReportOutcome,
)
from app.schemas.analyst import (
    AnalystCreate,
    AnalystOut,
    AnalystProfileResponse,
    AnalystStats,
    AnalystUpdate,
    LeaderboardItem,
    LeaderboardResponse,
)
from app.services.reports.accuracy import OutcomeSample, compute_analyst_accuracy

router = APIRouter()


async def _get_analyst_or_404(db: AsyncSession, analyst_id: UUID) -> Analyst:
    """按 id 取经纪人，不存在则 404。"""
    analyst = (
        await db.execute(select(Analyst).where(Analyst.id == analyst_id))
    ).scalar_one_or_none()
    if analyst is None:
        raise HTTPException(status_code=404, detail="经纪人不存在")
    return analyst


async def _compute_stats(db: AsyncSession, analyst_id: UUID) -> AnalystStats:
    """聚合某经纪人的报告数与准确率。"""
    total = (
        await db.execute(
            select(func.count()).select_from(Report).where(Report.analyst_id == analyst_id)
        )
    ).scalar_one()
    published = (
        await db.execute(
            select(func.count())
            .select_from(Report)
            .where(Report.analyst_id == analyst_id)
            .where(Report.status == REPORT_STATUS_PUBLISHED)
        )
    ).scalar_one()

    # 取该经纪人所有报告的回测结果
    stmt = (
        select(ReportOutcome.is_correct, ReportOutcome.actual_return_pct)
        .join(Report, Report.id == ReportOutcome.report_id)
        .where(Report.analyst_id == analyst_id)
    )
    rows = (await db.execute(stmt)).all()
    samples = [OutcomeSample(is_correct=r[0], actual_return_pct=r[1]) for r in rows]
    acc = compute_analyst_accuracy(samples)

    return AnalystStats(
        total_reports=int(total),
        published_reports=int(published),
        resolved_count=acc.resolved_count,
        correct_count=acc.correct_count,
        accuracy=acc.accuracy,
        avg_return_pct=acc.avg_return_pct,
    )


@router.post("/", response_model=AnalystOut, status_code=201)
async def create_analyst(
    payload: AnalystCreate,
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> AnalystOut:
    """成为经纪人（一人一档，重复建档返回 409）。"""
    existing = (
        await db.execute(select(Analyst).where(Analyst.user_id == user_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该账号已是经纪人")

    analyst = Analyst(
        user_id=user_id,
        display_name=payload.display_name,
        bio=payload.bio,
        avatar_url=payload.avatar_url,
        monthly_price_cents=payload.monthly_price_cents,
    )
    db.add(analyst)
    await db.commit()
    await db.refresh(analyst)
    logger.info("analyst_created", analyst_id=str(analyst.id), user_id=user_id)
    return AnalystOut.model_validate(analyst)


@router.get("/", response_model=list[AnalystOut])
async def list_analysts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[AnalystOut]:
    """经纪人列表。"""
    stmt = (
        select(Analyst)
        .where(Analyst.status == "active")
        .order_by(Analyst.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [AnalystOut.model_validate(a) for a in rows]


@router.get("/me", response_model=AnalystProfileResponse)
async def get_my_analyst(
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> AnalystProfileResponse:
    """当前账号的经纪人主页（未建档则 404）。"""
    analyst = (
        await db.execute(select(Analyst).where(Analyst.user_id == user_id))
    ).scalar_one_or_none()
    if analyst is None:
        raise HTTPException(status_code=404, detail="当前账号尚未成为经纪人")
    stats = await _compute_stats(db, analyst.id)
    return AnalystProfileResponse(analyst=AnalystOut.model_validate(analyst), stats=stats)


@router.patch("/me", response_model=AnalystOut)
async def update_my_analyst(
    payload: AnalystUpdate,
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> AnalystOut:
    """更新当前账号的经纪人档案。"""
    analyst = (
        await db.execute(select(Analyst).where(Analyst.user_id == user_id))
    ).scalar_one_or_none()
    if analyst is None:
        raise HTTPException(status_code=404, detail="当前账号尚未成为经纪人")
    data = payload.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(analyst, key, value)
    db.add(analyst)
    await db.commit()
    await db.refresh(analyst)
    return AnalystOut.model_validate(analyst)


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    min_resolved: int = Query(3, ge=0, description="已到期报告数下限，样本太少不上榜"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    """准确率榜单：按命中率降序，样本不足者过滤。"""
    analysts = (
        await db.execute(select(Analyst).where(Analyst.status == "active"))
    ).scalars().all()

    items: list[LeaderboardItem] = []
    for analyst in analysts:
        stats = await _compute_stats(db, analyst.id)
        if stats.resolved_count < min_resolved:
            continue
        items.append(
            LeaderboardItem(analyst=AnalystOut.model_validate(analyst), stats=stats)
        )

    # 命中率降序；并列时平均收益高者优先
    items.sort(
        key=lambda it: (it.stats.accuracy or 0.0, it.stats.avg_return_pct or 0.0),
        reverse=True,
    )
    return LeaderboardResponse(items=items[:limit], min_resolved=min_resolved)


@router.get("/{analyst_id}", response_model=AnalystProfileResponse)
async def get_analyst(
    analyst_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AnalystProfileResponse:
    """经纪人主页（公开）。"""
    analyst = await _get_analyst_or_404(db, analyst_id)
    stats = await _compute_stats(db, analyst.id)
    return AnalystProfileResponse(analyst=AnalystOut.model_validate(analyst), stats=stats)
