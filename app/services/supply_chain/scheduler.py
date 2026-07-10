"""Automatic weekly scheduling for supply-chain graph batch runs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import redis
from sqlmodel import select

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_sync_session_cm
from app.models.supply_chain_run import SupplyChainRun
from app.tasks.supply_chain import run_supply_chain_batch

SCHEDULE_SOURCE = "weekly_auto_scheduler"
# 用户删除某周的自动调度任务后，记一个跳过标记，避免调度器把它重建（下周自动恢复）。
_SKIP_KEY = "supply_chain:weekly_skip:{week_key}"
_SKIP_TTL_SECONDS = 8 * 24 * 3600
_skip_client: redis.Redis | None = None


def _get_skip_client() -> redis.Redis:
    global _skip_client
    if _skip_client is None:
        _skip_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    return _skip_client


def mark_week_skipped(week_key: str) -> None:
    """标记某周的自动调度任务已被用户删除，调度器本周不再重建."""
    try:
        _get_skip_client().set(_SKIP_KEY.format(week_key=week_key), "1", ex=_SKIP_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("supply_chain_weekly_skip_mark_failed", week_key=week_key, error=str(exc))


def is_week_skipped(week_key: str) -> bool:
    """Return True if the user deleted this week's scheduled run."""
    try:
        return _get_skip_client().get(_SKIP_KEY.format(week_key=week_key)) is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("supply_chain_weekly_skip_read_failed", week_key=week_key, error=str(exc))
        return False


def current_week_key(now: datetime | None = None) -> str:
    """Return a stable UTC weekly key for de-duplicating scheduled runs."""
    current = now or datetime.now(UTC)
    week_start = current - timedelta(days=current.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return week_start.date().isoformat()


def _is_scheduled_run(run: SupplyChainRun, week_key: str) -> bool:
    return run.params.get("source") == SCHEDULE_SOURCE and run.params.get("week_key") == week_key


def ensure_weekly_supply_chain_batch_run() -> str | None:
    """Create and enqueue the current weekly batch run if it does not already exist."""
    universe = settings.SUPPLY_CHAIN_UNIVERSE
    week_key = current_week_key()

    with get_sync_session_cm() as session:
        runs = session.exec(
            select(SupplyChainRun).where(
                SupplyChainRun.run_type == "batch",
                SupplyChainRun.universe == universe,
            ),
        ).all()
        existing = next((run for run in runs if _is_scheduled_run(run, week_key)), None)
        if existing is not None:
            if existing.status == "pending" and existing.total == 0:
                run_supply_chain_batch.delay(str(existing.id))  # pyright: ignore[reportFunctionMemberAccess]
                logger.info(
                    "supply_chain_weekly_batch_reenqueued",
                    run_id=str(existing.id),
                    universe=universe,
                    week_key=week_key,
                )
                return str(existing.id)
            logger.info(
                "supply_chain_weekly_batch_already_exists",
                run_id=str(existing.id),
                universe=universe,
                week_key=week_key,
                status=existing.status,
            )
            return None

        if is_week_skipped(week_key):
            logger.info("supply_chain_weekly_batch_skipped_user_deleted", universe=universe, week_key=week_key)
            return None

        run = SupplyChainRun(
            run_type="batch",
            universe=universe,
            status="pending",
            params={"source": SCHEDULE_SOURCE, "week_key": week_key},
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_supply_chain_batch.delay(str(run.id))  # pyright: ignore[reportFunctionMemberAccess]
        logger.info("supply_chain_weekly_batch_enqueued", run_id=str(run.id), universe=universe, week_key=week_key)
        return str(run.id)


async def run_weekly_supply_chain_scheduler() -> None:
    """Ensure one supply-chain graph batch exists each week while the API process is alive."""
    while True:
        try:
            await asyncio.to_thread(ensure_weekly_supply_chain_batch_run)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("supply_chain_weekly_scheduler_failed", error=str(exc))
        await asyncio.sleep(settings.SUPPLY_CHAIN_WEEKLY_SCHEDULER_INTERVAL_SECONDS)
