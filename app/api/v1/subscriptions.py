"""订阅 API：订阅经纪人 / 平台、我的订阅、取消。

第一版不接真实支付网关：按经纪人月费 * 月数计算 price_cents 并直接置为 ACTIVE。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth.dependencies import get_verified_user_id
from app.core.logging import logger
from app.db.session import get_db
from app.models.analyst import Analyst
from app.models.subscription import (
    SUB_STATUS_ACTIVE,
    SUB_STATUS_CANCELED,
    TIER_ANALYST,
    Subscription,
)
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionListResponse,
    SubscriptionOut,
)

router = APIRouter()

# 订阅平台的月费（分），后续可移入平台配置
PLATFORM_MONTHLY_PRICE_CENTS = 9900


@router.post("/", response_model=SubscriptionOut, status_code=201)
async def create_subscription(
    payload: SubscriptionCreate,
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    """创建订阅（经纪人 / 平台）。"""
    try:
        payload.validate_semantics()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = datetime.now(UTC)
    end_at = now + timedelta(days=30 * payload.months)

    if payload.tier == TIER_ANALYST:
        analyst = (
            await db.execute(select(Analyst).where(Analyst.id == payload.analyst_id))
        ).scalar_one_or_none()
        if analyst is None:
            raise HTTPException(status_code=404, detail="经纪人不存在")
        if analyst.user_id == user_id:
            raise HTTPException(status_code=400, detail="不能订阅自己")
        price_cents = analyst.monthly_price_cents * payload.months
    else:
        price_cents = PLATFORM_MONTHLY_PRICE_CENTS * payload.months

    sub = Subscription(
        user_id=user_id,
        tier=payload.tier,
        analyst_id=payload.analyst_id,
        status=SUB_STATUS_ACTIVE,
        price_cents=price_cents,
        start_at=now,
        end_at=end_at,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    logger.info(
        "subscription_created",
        subscription_id=str(sub.id),
        user_id=user_id,
        tier=sub.tier,
    )
    return SubscriptionOut.model_validate(sub)


@router.get("/me", response_model=SubscriptionListResponse)
async def list_my_subscriptions(
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionListResponse:
    """我的订阅。"""
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
    )
    subs = (await db.execute(stmt)).scalars().all()
    return SubscriptionListResponse(
        items=[SubscriptionOut.model_validate(s) for s in subs]
    )


@router.delete("/{subscription_id}", response_model=SubscriptionOut)
async def cancel_subscription(
    subscription_id: UUID,
    user_id: int = Depends(get_verified_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    """取消订阅（置为 CANCELED，立即失去访问权）。

    第一版从简：CANCELED 即刻失效。后续接入支付后可改为「取消自动续费、
    到期前仍可见」以尊重已付费权益。
    """
    sub = (
        await db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    if sub.user_id != user_id:
        raise HTTPException(status_code=403, detail="只能取消自己的订阅")
    sub.status = SUB_STATUS_CANCELED
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return SubscriptionOut.model_validate(sub)
