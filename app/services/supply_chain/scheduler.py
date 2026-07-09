"""Automatic weekly scheduling for supply-chain graph batch runs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_sync_session_cm
from app.models.supply_chain_run import SupplyChainRun
from app.tasks.supply_chain import run_supply_chain_batch

SCHEDULE_SOURCE = "weekly_auto_scheduler"


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
