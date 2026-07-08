"""Celery orchestration for supply-chain graph runs."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_sync_session_cm
from app.models.supply_chain_run import SupplyChainRun
from app.models.supply_chain_task import SupplyChainTask
from app.services.llm.service import LLMQuotaExhausted, llm_service
from app.services.supply_chain.fmp_universe import FMPUniverse
from app.services.supply_chain.pipeline import run_company_pipeline


@celery_app.task(name="supply_chain.run_batch")
def run_supply_chain_batch(run_id: str) -> dict:
    """Enumerate a configured universe and queue one task per company."""
    run_uuid = uuid.UUID(run_id)
    universe = FMPUniverse()
    companies = asyncio.run(universe.load())
    with get_sync_session_cm() as session:
        run = session.get(SupplyChainRun, run_uuid)
        if run is None:
            return {"missing": True}
        symbols = [company.symbol for company in companies]
        if run.universe == "nasdaq100":
            symbols = [company.symbol for company in companies if company.exchange.upper() == "NASDAQ"][:100]
        elif run.universe == "sp500":
            symbols = symbols[:500]
        elif run.universe == "russell1000":
            symbols = symbols[:1000]
        run.total, run.status = len(symbols), "running"
        for ticker in symbols:
            task = SupplyChainTask(run_id=run_uuid, ticker=ticker)
            session.add(task)
            session.flush()
            queued = process_company.delay(run_id, ticker)  # pyright: ignore[reportFunctionMemberAccess]
            task.celery_task_id = queued.id
        if not symbols:
            run.status, run.finished_at = "done", datetime.now(UTC)
        session.commit()
    return {"queued": len(symbols)}


@celery_app.task(name="supply_chain.process_company", bind=True, max_retries=3)
def process_company(self, run_id: str, ticker: str) -> dict:
    """Process one company inside a single event loop."""
    run_uuid = uuid.UUID(run_id)
    with get_sync_session_cm() as session:
        run = session.get(SupplyChainRun, run_uuid)
        task = session.exec(select(SupplyChainTask).where(SupplyChainTask.run_id == run_uuid, SupplyChainTask.ticker == ticker)).first()
        if run is None or task is None:
            return {"missing": True}
        if run.status in {"paused", "paused_quota"}:
            countdown = max(60, int(((run.resume_after or datetime.now(UTC) + timedelta(minutes=5)) - datetime.now(UTC)).total_seconds()))
            process_company.apply_async(args=[run_id, ticker], countdown=countdown)  # pyright: ignore[reportFunctionMemberAccess]
            return {"paused": True}
        task.status, task.started_at = "running", datetime.now(UTC)
        run.status, run.started_at = "running", run.started_at or datetime.now(UTC)
        session.commit()
        try:
            result = asyncio.run(run_company_pipeline(ticker, run_uuid, session, llm_service, FMPUniverse()))
        except LLMQuotaExhausted as exc:
            resume_after = datetime.now(UTC) + timedelta(seconds=exc.retry_after_hint or settings.SUPPLY_CHAIN_QUOTA_WINDOW_SECONDS)
            task.status, task.resume_after, task.quota_retries = "paused_quota", resume_after, task.quota_retries + 1
            run.status, run.quota_paused_at, run.resume_after = "paused_quota", datetime.now(UTC), resume_after
            session.commit()
            resume_run_if_quota_recovered.apply_async(args=[run_id], countdown=max(60, int((resume_after - datetime.now(UTC)).total_seconds())))  # pyright: ignore[reportFunctionMemberAccess]
            return {"paused_quota": True}
        except Exception as exc:
            task.retries += 1
            task.status, task.error = ("retrying" if task.retries <= task.max_retries else "failed"), str(exc)
            session.commit()
            logger.exception("supply_chain_company_failed", ticker=ticker, run_id=run_id)
            raise self.retry(exc=exc, countdown=min(600, 2 ** task.retries))
        task.status, task.stage, task.result_summary, task.finished_at = "success", "EVIDENCE_VERIFY", result, datetime.now(UTC)
        run.completed += 1
        if run.completed + run.failed >= run.total:
            run.status, run.finished_at = "done", datetime.now(UTC)
        session.commit()
        return result


@celery_app.task(name="supply_chain.resume_run")
def resume_run_if_quota_recovered(run_id: str) -> None:
    """Probe quota and requeue paused tasks."""
    run_uuid = uuid.UUID(run_id)
    try:
        asyncio.run(llm_service.call([{"role": "user", "content": "ping"}], timeout=15))
    except LLMQuotaExhausted:
        with get_sync_session_cm() as session:
            run = session.get(SupplyChainRun, run_uuid)
            if run is None:
                return
            run.probe_attempts += 1
            if run.probe_attempts >= settings.SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS:
                run.status = "failed"
                session.commit()
                return
            session.commit()
        delay = min(900, settings.SUPPLY_CHAIN_PROBE_BACKOFF_SECONDS * (5 ** max(0, run.probe_attempts - 1)))
        resume_run_if_quota_recovered.apply_async(args=[run_id], countdown=delay)  # pyright: ignore[reportFunctionMemberAccess]
        return
    with get_sync_session_cm() as session:
        run = session.get(SupplyChainRun, run_uuid)
        if run is None:
            return
        run.status, run.probe_attempts = "running", 0
        tasks = session.exec(select(SupplyChainTask).where(SupplyChainTask.run_id == run_uuid, SupplyChainTask.status == "paused_quota")).all()
        for task in tasks:
            task.status, task.resume_after = "queued", None
            process_company.delay(run_id, task.ticker)  # pyright: ignore[reportFunctionMemberAccess]
        session.commit()
