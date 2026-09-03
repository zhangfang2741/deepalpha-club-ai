"""报告订阅门控（可见性）测试。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.report import VISIBILITY_PUBLIC, VISIBILITY_SUBSCRIBER
from app.models.subscription import (
    SUB_STATUS_ACTIVE,
    SUB_STATUS_CANCELED,
    TIER_ANALYST,
    TIER_PLATFORM,
)
from app.services.reports.access import SubscriptionView, can_view_content

NOW = datetime(2026, 9, 1, tzinfo=UTC)
FUTURE = NOW + timedelta(days=30)
PAST = NOW - timedelta(days=1)


def _sub(tier, analyst_id=None, status=SUB_STATUS_ACTIVE, end_at=FUTURE):
    return SubscriptionView(tier=tier, analyst_id=analyst_id, status=status, end_at=end_at)


def test_public_report_visible_to_anyone():
    assert (
        can_view_content(
            viewer_user_id=None,
            report_analyst_user_id=1,
            report_analyst_id=uuid4(),
            report_visibility=VISIBILITY_PUBLIC,
            subscriptions=[],
            now=NOW,
        )
        is True
    )


def test_anonymous_cannot_view_subscriber_report():
    assert (
        can_view_content(
            viewer_user_id=None,
            report_analyst_user_id=1,
            report_analyst_id=uuid4(),
            report_visibility=VISIBILITY_SUBSCRIBER,
            subscriptions=[],
            now=NOW,
        )
        is False
    )


def test_author_can_view_own_report():
    assert (
        can_view_content(
            viewer_user_id=42,
            report_analyst_user_id=42,
            report_analyst_id=uuid4(),
            report_visibility=VISIBILITY_SUBSCRIBER,
            subscriptions=[],
            now=NOW,
        )
        is True
    )


def test_platform_subscription_unlocks_all():
    assert (
        can_view_content(
            viewer_user_id=7,
            report_analyst_user_id=1,
            report_analyst_id=uuid4(),
            report_visibility=VISIBILITY_SUBSCRIBER,
            subscriptions=[_sub(TIER_PLATFORM)],
            now=NOW,
        )
        is True
    )


def test_analyst_subscription_matches_only_that_analyst():
    target = uuid4()
    other = uuid4()
    # 订阅了 target
    assert (
        can_view_content(
            viewer_user_id=7,
            report_analyst_user_id=1,
            report_analyst_id=target,
            report_visibility=VISIBILITY_SUBSCRIBER,
            subscriptions=[_sub(TIER_ANALYST, analyst_id=target)],
            now=NOW,
        )
        is True
    )
    # 订阅的是别人 -> 看不了 target
    assert (
        can_view_content(
            viewer_user_id=7,
            report_analyst_user_id=1,
            report_analyst_id=target,
            report_visibility=VISIBILITY_SUBSCRIBER,
            subscriptions=[_sub(TIER_ANALYST, analyst_id=other)],
            now=NOW,
        )
        is False
    )


def test_expired_or_canceled_subscription_locks():
    a = uuid4()
    # 已过期
    assert (
        can_view_content(
            viewer_user_id=7,
            report_analyst_user_id=1,
            report_analyst_id=a,
            report_visibility=VISIBILITY_SUBSCRIBER,
            subscriptions=[_sub(TIER_PLATFORM, end_at=PAST)],
            now=NOW,
        )
        is False
    )
    # 已取消
    assert (
        can_view_content(
            viewer_user_id=7,
            report_analyst_user_id=1,
            report_analyst_id=a,
            report_visibility=VISIBILITY_SUBSCRIBER,
            subscriptions=[_sub(TIER_ANALYST, analyst_id=a, status=SUB_STATUS_CANCELED)],
            now=NOW,
        )
        is False
    )
