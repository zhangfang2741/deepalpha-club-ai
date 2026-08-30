"""交易台路由。

本层只做请求解析、参数校验、调用 service、返回响应（项目分层规则）。

SSE 说明：事件从 Redis Stream 消费，每条同时写 SSE 的 id 字段（Redis
Stream ID）。前端断线重连时把它放进 Last-Event-ID 请求头即可续读，
既不漏事件也不重复。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.auth.dependencies import get_current_user
from app.cache.client import get_redis
from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.trading_desk import (
    ControlAction,
    ControlRequest,
    ControlResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunDetailResponse,
    RunListResponse,
    RunSummary,
)
from app.services.trading_desk import event_bus, persistence, runner
from app.services.trading_desk.engine_base import TradingEngine
from app.services.trading_desk.engines.mock import MockEngine

router = APIRouter()


_tradingagents_engine: TradingEngine | None = None
_tradingagents_lock = asyncio.Lock()


async def _build_tradingagents_engine() -> TradingEngine:
    """进程级单例的 TradingAgentsEngine。

    checkpointer 必须显式传入 AsyncPostgresSaver（生产）——LangGraph 要求
    interrupt_before 与 checkpointer 配套使用，否则 compile() 抛
    "No checkpointer set"。

    连接池从 graph.py 的 LangGraph 同款 PostgreSQL 设置搭出来，避免再开
    一个数据库连接池。
    """
    from urllib.parse import quote_plus

    from psycopg import AsyncConnection
    from psycopg.rows import DictRow
    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.services.trading_desk.engines.tradingagents import TradingAgentsEngine

    connection_url = (
        "postgresql://"
        f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    checkpointer = None
    try:
        pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
            connection_url,
            open=False,
            max_size=settings.POSTGRES_POOL_SIZE,
            kwargs={"autocommit": True, "connect_timeout": 5, "sslmode": "require" if settings.POSTGRES_SSL else "disable"},
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await checkpointer.setup()
    except Exception:
        logger.exception("trading_desk_checkpointer_init_failed")
        # Postgres 不可用时降级用 InMemorySaver：同进程能跑，重启即丢状态
        checkpointer = InMemorySaver()

    return TradingAgentsEngine(checkpointer=checkpointer)


async def get_engine() -> TradingEngine:
    """按配置选择引擎（async：tradingagents 引擎需要异步构造 checkpointer）。

    接入策略：
      - ``mock`` → MockEngine（固定剧本，无需 LLM）。
      - ``tradingagents`` → TradingAgentsEngine（真实多 Agent 图，checkpointer
        进程内单例,避免每次请求重建连接池）。
      - 其它或缺配置 → MockEngine 并警告（保留默认行为不让生产翻车）。
    """
    if settings.TRADING_DESK_ENGINE == "tradingagents":
        global _tradingagents_engine
        if _tradingagents_engine is None:
            async with _tradingagents_lock:
                if _tradingagents_engine is None:
                    _tradingagents_engine = await _build_tradingagents_engine()
        return _tradingagents_engine
    if settings.TRADING_DESK_ENGINE == "mock":
        return MockEngine()
    logger.warning(
        "trading_desk_engine_unknown_value",
        requested=settings.TRADING_DESK_ENGINE,
        fallback="mock",
    )
    return MockEngine()


@router.post("/runs", response_model=CreateRunResponse)
async def create_run(
    payload: CreateRunRequest,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
    engine: Annotated[TradingEngine, Depends(get_engine)],
) -> CreateRunResponse:
    """创建一次分析运行，立即返回 run_id；实际执行在后台进行。"""
    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="标的代码不能为空",
        )

    trade_date = payload.trade_date or datetime.now(UTC).strftime("%Y-%m-%d")
    run_id = await runner.start_run(
        redis, user_id=user.id, ticker=ticker, trade_date=trade_date, engine=engine,
    )
    return CreateRunResponse(run_id=run_id)


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """以 SSE 推送事件流，支持 Last-Event-ID 断线续读。"""
    # 先确认 run 存在：否则订阅会一路轮询到空闲超时（默认 5 分钟），
    # 白占一条连接，前端也拿不到任何反馈。
    if not await event_bus.exists(redis, run_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="运行不存在或事件流已过期",
        )

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for stream_id, event in event_bus.subscribe(redis, run_id, last_id=last_event_id):
                yield f"id: {stream_id}\ndata: {event.model_dump_json()}\n\n"
        except Exception:
            logger.exception("trading_desk_stream_failed", run_id=run_id)
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/control", response_model=ControlResponse)
async def control_run(
    run_id: str,
    payload: ControlRequest,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ControlResponse:
    """暂停 / 恢复 / 注入人工意见 / 取消。引擎在下一个节点边界响应。"""
    text = (payload.text or "").strip()
    if payload.action is ControlAction.INJECT and not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="注入意见时 text 不能为空",
        )

    match payload.action:
        case ControlAction.PAUSE:
            await runner.pause(redis, run_id)
        case ControlAction.RESUME:
            await runner.resume(redis, run_id)
        case ControlAction.CANCEL:
            await runner.cancel(redis, run_id)
        case ControlAction.INJECT:
            await runner.inject(redis, run_id, text)

    return ControlResponse(accepted=True)


# ── 历史回放 ────────────────────────────────────────────────────────


def _to_summary(row: Any) -> RunSummary:
    """行 → 列表摘要。verdict/signals/turns 是 JSON 列，python 已是 dict/list。

    finished_at 允许 None（运行中 / 进程崩溃），直接 None。
    """
    verdict = row.verdict
    turns = row.turns or []
    signals = row.signals or []
    return RunSummary(
        run_id=str(row.id),
        ticker=row.ticker,
        trade_date=row.trade_date,
        engine=row.engine,
        status=row.status,
        duration_ms=row.duration_ms,
        created_at=row.created_at.isoformat() if row.created_at else "",
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        verdict_signal=verdict.get("signal") if isinstance(verdict, dict) else None,
        verdict_confidence=verdict.get("confidence") if isinstance(verdict, dict) else None,
        turns_count=len(turns) if isinstance(turns, list) else 0,
        signals_count=len(signals) if isinstance(signals, list) else 0,
    )


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    ticker: Annotated[str | None, Query(description="按标的过滤")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunListResponse:
    """列某用户最近的分析 run（按 ticker 过滤可选）。

    只返回摘要字段（不含 turns/signals 全文），保持列表查询快、传输小；
    详情请走 GET /runs/{run_id}。
    """
    rows = await persistence.list_runs(
        db, user_id=user.id, ticker=ticker, limit=limit, offset=offset
    )
    return RunListResponse(runs=[_to_summary(r) for r in rows])


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunDetailResponse:
    """取一条 run 的全部持久化字段：turns/signals/verdict 全文。

    越权访问走与 404 同一路径：行不存在或不属于当前用户，都返回 404，
    避免泄漏别的用户的 run_id。
    """
    row = await persistence.get_run(db, run_id=run_id, user_id=user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="运行不存在",
        )
    return RunDetailResponse(
        run_id=str(row.id),
        ticker=row.ticker,
        trade_date=row.trade_date,
        engine=row.engine,
        status=row.status,
        duration_ms=row.duration_ms,
        created_at=row.created_at.isoformat() if row.created_at else "",
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        verdict=row.verdict,
        signals=row.signals or [],
        turns=row.turns or [],
    )
