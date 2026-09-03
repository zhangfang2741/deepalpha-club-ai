"""报告可见性（订阅门控）纯逻辑。

判定用户能否看到某报告的正文；DB 取数由 API 层完成，这里只做规则判断。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Optional
from uuid import UUID

from app.models.report import VISIBILITY_PUBLIC
from app.models.subscription import (
    SUB_STATUS_ACTIVE,
    TIER_ANALYST,
    TIER_PLATFORM,
)


@dataclass
class SubscriptionView:
    """参与门控判断的订阅精简视图。"""

    tier: str
    analyst_id: Optional[UUID]
    status: str
    end_at: datetime


def _is_active(sub: SubscriptionView, now: datetime) -> bool:
    """订阅当前是否有效。"""
    return sub.status == SUB_STATUS_ACTIVE and sub.end_at > now


def can_view_content(
    *,
    viewer_user_id: Optional[int],
    report_analyst_user_id: int,
    report_analyst_id: UUID,
    report_visibility: str,
    subscriptions: Iterable[SubscriptionView],
    now: Optional[datetime] = None,
) -> bool:
    """判断 viewer 能否看到该报告正文。

    Args:
        viewer_user_id: 浏览者 user_id（未登录传 None）。
        report_analyst_user_id: 报告作者（经纪人）对应的 User.id。
        report_analyst_id: 报告作者的 Analyst.id。
        report_visibility: 报告可见性。
        subscriptions: 浏览者的订阅集合。
        now: 判定基准时间（默认当前 UTC），供测试注入。
    """
    now = now or datetime.now(UTC)

    # 1. 公开样例
    if report_visibility == VISIBILITY_PUBLIC:
        return True

    # 未登录：只能看公开
    if viewer_user_id is None:
        return False

    # 2. 作者本人
    if viewer_user_id == report_analyst_user_id:
        return True

    # 3 / 4. 有效订阅
    for sub in subscriptions:
        if not _is_active(sub, now):
            continue
        if sub.tier == TIER_PLATFORM:
            return True
        if sub.tier == TIER_ANALYST and sub.analyst_id == report_analyst_id:
            return True

    return False
