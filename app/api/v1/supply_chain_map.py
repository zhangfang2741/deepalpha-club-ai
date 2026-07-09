"""Company-centric supply-chain graph API."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from app.core.celery_app import celery_app
from app.core.limiter import limiter
from app.core.logging import logger
from app.db.session import get_sync_session
from app.models.supply_chain_clue import SupplyChainClue
from app.models.supply_chain_node import SupplyChainNode
from app.models.supply_chain_run import SupplyChainRun
from app.models.supply_chain_task import SupplyChainTask
from app.schemas.supply_chain_map import RunCreate, RunCreated
from app.services.supply_chain.graph_query import query_neighborhood
from app.tasks.supply_chain import process_company, resume_run_if_quota_recovered, run_supply_chain_batch

router = APIRouter()


@router.post("/companies/{ticker}/run", response_model=RunCreated)
@limiter.limit("10/minute")
def run_company(request: Request, ticker: str, session: Session = Depends(get_sync_session)) -> RunCreated:
    """Queue one company pipeline."""
    ticker = ticker.upper()
    run = SupplyChainRun(run_type="single", universe=ticker, status="pending", total=1, params={})
    session.add(run)
    session.commit()
    session.refresh(run)
    task = SupplyChainTask(run_id=run.id, ticker=ticker)
    session.add(task)
    session.commit()
    result = process_company.delay(str(run.id), ticker)  # pyright: ignore[reportFunctionMemberAccess]
    task.celery_task_id = result.id
    session.commit()
    return RunCreated(run_id=run.id, status=run.status)


@router.post("/runs", response_model=RunCreated)
@limiter.limit("5/minute")
def create_run(request: Request, body: RunCreate, session: Session = Depends(get_sync_session)) -> RunCreated:
    """Create a batch run; ticker enumeration is intentionally provider-driven."""
    run = SupplyChainRun(run_type="batch", universe=body.universe, status="pending", params=body.params)
    session.add(run)
    session.commit()
    session.refresh(run)
    run_supply_chain_batch.delay(str(run.id))  # pyright: ignore[reportFunctionMemberAccess]
    return RunCreated(run_id=run.id, status=run.status)


@router.get("/worker-status")
@limiter.limit("60/minute")
def worker_status(request: Request) -> dict:
    """Ping Celery workers so the UI can tell online from offline.

    通过 Celery 控制通道广播 ping，只有正在消费队列的 worker 会回应；
    无回应即视为离线（部署未起 worker / worker 已停）。
    """
    try:
        replies = celery_app.control.ping(timeout=1.0) or []
    except Exception as exc:
        logger.warning("supply_chain_worker_ping_failed", error=str(exc))
        return {"online": False, "count": 0, "workers": [], "error": "broker_unreachable"}
    workers = [name for reply in replies for name in reply]
    return {"online": len(workers) > 0, "count": len(workers), "workers": workers}


@router.get("/runs")
@limiter.limit("60/minute")
def list_runs(request: Request, session: Session = Depends(get_sync_session)) -> list[SupplyChainRun]:
    """List newest runs."""
    runs = list(session.exec(select(SupplyChainRun)))
    return sorted(runs, key=lambda run: run.created_at, reverse=True)[:100]


@router.get("/runs/{run_id}")
@limiter.limit("60/minute")
def get_run(request: Request, run_id: uuid.UUID, session: Session = Depends(get_sync_session)) -> dict:
    """Return a run and its tasks."""
    run = session.get(SupplyChainRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    tasks = list(session.exec(select(SupplyChainTask).where(SupplyChainTask.run_id == run_id)))
    return {"run": run, "tasks": tasks}


@router.post("/runs/{run_id}/pause")
@limiter.limit("20/minute")
def pause_run(request: Request, run_id: uuid.UUID, session: Session = Depends(get_sync_session)) -> dict:
    """Pause a run at the worker execution boundary."""
    run = session.get(SupplyChainRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    run.status = "paused"
    session.commit()
    return {"status": run.status}


@router.post("/runs/{run_id}/resume")
@limiter.limit("20/minute")
def resume_run(request: Request, run_id: uuid.UUID, session: Session = Depends(get_sync_session)) -> dict:
    """Resume manually; quota-paused runs are probed first."""
    run = session.get(SupplyChainRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status == "paused_quota":
        resume_run_if_quota_recovered.delay(str(run_id))  # pyright: ignore[reportFunctionMemberAccess]
    else:
        run.status = "running"
        tasks = session.exec(select(SupplyChainTask).where(SupplyChainTask.run_id == run_id, SupplyChainTask.status == "queued")).all()
        for task in tasks:
            process_company.delay(str(run_id), task.ticker)  # pyright: ignore[reportFunctionMemberAccess]
        session.commit()
    return {"status": "resuming"}


@router.post("/runs/{run_id}/retry-failed")
@limiter.limit("20/minute")
def retry_failed(request: Request, run_id: uuid.UUID, session: Session = Depends(get_sync_session)) -> dict:
    """Requeue failed company tasks."""
    tasks = session.exec(select(SupplyChainTask).where(SupplyChainTask.run_id == run_id, SupplyChainTask.status == "failed")).all()
    for task in tasks:
        task.status, task.error = "queued", None
        process_company.delay(str(run_id), task.ticker)  # pyright: ignore[reportFunctionMemberAccess]
    session.commit()
    return {"requeued": len(tasks)}


@router.post("/runs/{run_id}/restart")
@limiter.limit("20/minute")
def restart_run(request: Request, run_id: uuid.UUID, session: Session = Depends(get_sync_session)) -> dict:
    """Re-trigger a stuck run whose orchestration never produced subtasks.

    针对停在"待处理/失败"且未成功枚举的 run：清掉旧子任务后重新入队编排任务
    （批次）或重新执行单公司任务，让 worker 恢复后能继续。
    """
    run = session.get(SupplyChainRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    # 仅拦截"确有进度的运行中"任务；0 进度的卡死任务允许重启
    if run.status == "running" and run.total > 0 and 0 < run.completed + run.failed < run.total:
        raise HTTPException(409, "run is progressing; use pause/resume/retry-failed instead")
    old_tasks = session.exec(select(SupplyChainTask).where(SupplyChainTask.run_id == run_id)).all()
    for task in old_tasks:
        session.delete(task)
    run.status, run.total, run.completed, run.failed = "pending", 0, 0, 0
    run.started_at = run.finished_at = run.quota_paused_at = run.resume_after = None
    run.probe_attempts = 0
    run.params = {key: value for key, value in run.params.items() if key != "error"}
    session.commit()
    if run.run_type == "batch":
        run_supply_chain_batch.delay(str(run_id))  # pyright: ignore[reportFunctionMemberAccess]
    else:
        ticker = run.universe.upper()
        task = SupplyChainTask(run_id=run_id, ticker=ticker)
        run.total = 1
        session.add(task)
        session.commit()
        result = process_company.delay(str(run_id), ticker)  # pyright: ignore[reportFunctionMemberAccess]
        task.celery_task_id = result.id
        session.commit()
    return {"status": "restarting"}


@router.get("/graph")
@limiter.limit("120/minute")
def get_graph(request: Request, ticker: str, depth: int = Query(1, ge=1, le=3), direction: str = "both", session: Session = Depends(get_sync_session)) -> dict:
    """Return a bounded neighborhood around a ticker."""
    result = query_neighborhood(session, ticker, depth, direction)
    return {**result.graph.to_dict(), "truncated": result.truncated}


@router.get("/graph/expand")
@limiter.limit("120/minute")
def expand_graph(request: Request, from_node_id: str, depth: int = Query(1, ge=1, le=3), direction: str = "both", session: Session = Depends(get_sync_session)) -> dict:
    """Incrementally fetch a neighborhood around the current focus."""
    result = query_neighborhood(session, from_node_id, depth, direction)
    return {**result.graph.to_dict(), "truncated": result.truncated}


@router.get("/edges/{edge_id}/clues")
@limiter.limit("120/minute")
def edge_clues(request: Request, edge_id: str, session: Session = Depends(get_sync_session)) -> list[SupplyChainClue]:
    """Return newest evidence clues for an edge."""
    clues = list(session.exec(select(SupplyChainClue).where(SupplyChainClue.edge_id == edge_id)))
    return sorted(clues, key=lambda clue: clue.filing_date or clue.created_at.date(), reverse=True)


@router.get("/nodes/{node_id}/detail")
@limiter.limit("120/minute")
def node_detail(request: Request, node_id: str, session: Session = Depends(get_sync_session)) -> SupplyChainNode:
    """Return node profile."""
    node = session.exec(select(SupplyChainNode).where(SupplyChainNode.node_id == node_id)).first()
    if node is None:
        raise HTTPException(404, "node not found")
    return node
