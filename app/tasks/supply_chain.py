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


async def _fetch_universe_symbols(universe: str) -> list[str]:
    """复用 analyst_upgrade 的 Wikipedia 成分股抓取（含兜底），返回去重后的 symbol 列表。

    sp500 / nasdaq100 走维基（FMP 无成分股权限也可用）；其它 universe 返回空，交由调用方回退。
    """
    import httpx

    from app.services.analyst_upgrade.nasdaq100 import _fetch_constituents
    from app.services.analyst_upgrade.sp500 import _fetch_sp500_constituents

    if universe not in {"sp500", "nasdaq100"}:
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        rows = (
            await _fetch_sp500_constituents(client)
            if universe == "sp500"
            else await _fetch_constituents(client)
        )
    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").upper().strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


@celery_app.task(name="supply_chain.run_batch")
def run_supply_chain_batch(run_id: str) -> dict:
    """Enumerate a configured universe and queue one task per company."""
    run_uuid = uuid.UUID(run_id)
    # 立即标记 running，避免枚举阶段（较慢）期间界面一直显示"待处理"
    with get_sync_session_cm() as session:
        run = session.get(SupplyChainRun, run_uuid)
        if run is None:
            return {"missing": True}
        run.status, run.started_at = "running", run.started_at or datetime.now(UTC)
        session.commit()
    try:
        universe = FMPUniverse()
        companies = asyncio.run(universe.load())
    except Exception as exc:
        # 枚举失败（FMP 报错/无 key/网络）时显式置 failed，避免永远静默卡在待处理
        with get_sync_session_cm() as session:
            run = session.get(SupplyChainRun, run_uuid)
            if run is not None:
                run.status, run.finished_at = "failed", datetime.now(UTC)
                run.params = {**run.params, "error": str(exc)}
                session.commit()
        logger.exception("supply_chain_batch_enumerate_failed", run_id=run_id)
        return {"failed": True, "error": str(exc)}
    # 复用 analyst_upgrade 里的 Wikipedia 成分股抓取（带兜底列表），FMP 无成分股权限也能用。
    with get_sync_session_cm() as session:
        run = session.get(SupplyChainRun, run_uuid)
        if run is None:
            return {"missing": True}
        constituents: list[str] = []
        try:
            constituents = asyncio.run(_fetch_universe_symbols(run.universe))
        except Exception as exc:  # noqa: BLE001 - 成分股抓取失败则回退切片
            logger.warning("supply_chain_constituents_failed", run_id=run_id, universe=run.universe, error=str(exc))
            constituents = []
        if constituents:
            symbols = constituents
        else:
            # 无对应成分股来源（如 russell1000）时回退到 stock-list 切片
            symbols = [company.symbol for company in companies]
            if run.universe == "nasdaq100":
                symbols = [company.symbol for company in companies if company.exchange.upper() == "NASDAQ"][:100]
            elif run.universe == "sp500":
                symbols = symbols[:500]
            elif run.universe == "russell1000":
                symbols = symbols[:1000]
        if not symbols:
            # 成分股为空（多为缺 FMP_API_KEY 或接口异常）——置 failed 并说明，避免误报"已完成"
            run.status, run.finished_at = "failed", datetime.now(UTC)
            run.params = {**run.params, "error": "成分股列表为空，请检查 FMP_API_KEY 与行情接口"}
            session.commit()
            return {"queued": 0, "empty": True}
        # 先落库：total + 全部子任务行，一次性提交。
        # 必须在入队 process_company 之前提交，否则 worker 抢先执行时查不到子任务行（竞态）。
        run.total, run.status = len(symbols), "running"
        for ticker in symbols:
            session.add(SupplyChainTask(run_id=run_uuid, ticker=ticker))
        session.commit()
    # 子任务行已落库，再逐个入队；单个入队失败不影响其余，未入队的留在 queued，可用「继续」续跑。
    task_ids: dict[str, str] = {}
    for ticker in symbols:
        try:
            queued = process_company.delay(run_id, ticker)  # pyright: ignore[reportFunctionMemberAccess]
            task_ids[ticker] = queued.id
        except Exception as exc:  # noqa: BLE001 - 单个入队失败不应中断整批
            logger.warning("supply_chain_enqueue_failed", run_id=run_id, ticker=ticker, error=str(exc))
    # 批量回填 celery_task_id（一次提交，非关键元数据）。
    if task_ids:
        with get_sync_session_cm() as session:
            for task in session.exec(select(SupplyChainTask).where(SupplyChainTask.run_id == run_uuid)):
                task_id = task_ids.get(task.ticker)
                if task_id is not None:
                    task.celery_task_id = task_id
            session.commit()
    return {"queued": len(task_ids), "total": len(symbols)}


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
            terminal_failure = task.retries > task.max_retries
            task.status, task.error = ("failed" if terminal_failure else "retrying"), str(exc)
            if terminal_failure:
                run.failed += 1
                if run.completed + run.failed >= run.total:
                    run.status, run.finished_at = "done", datetime.now(UTC)
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
