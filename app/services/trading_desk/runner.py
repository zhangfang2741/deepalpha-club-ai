"""交易台运行编排。

职责边界：
  - runner 负责生命周期（run.started / run.finished / error）与控制信号，
    引擎只负责产出中间事件。这样所有引擎的生命周期语义一致，前端不必
    为每个引擎写特例。
  - 运行跑在后台 asyncio 任务里，HTTP 请求立即返回 run_id；SSE 端点是
    独立的消费者，断开不影响运行。

已知取舍：web 进程重启会中断在跑的 run（spec §11）。研究工具可接受，
且事件流已落 Redis，partial 结果仍可见。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Literal

from redis.asyncio import Redis

from app.cache import trading_desk_cache as tdc
from app.core.logging import logger
from app.schemas.trading_desk import (
    ErrorData,
    EventType,
    RunFinishedData,
    RunStartedData,
    TradingDeskEvent,
)
from app.services.trading_desk import event_bus
from app.services.trading_desk.engine_base import ControlHandle, RunContext, TradingEngine

RunStatus = Literal["completed", "cancelled", "failed", "interrupted"]

# run_id -> 后台任务。仅用于同进程内的 wait_for / 观测；
# 控制信号一律走 Redis，不依赖这个字典（进程重启后它会空掉）。
_TASKS: dict[str, asyncio.Task[None]] = {}


async def start_run(
    redis: Redis,
    *,
    ticker: str,
    trade_date: str,
    engine: TradingEngine,
) -> str:
    """创建一次运行并立即返回 run_id，实际执行在后台进行。"""
    run_id = uuid.uuid4().hex
    await tdc.init_control(redis, run_id)

    task = asyncio.create_task(_execute(redis, run_id, ticker, trade_date, engine))
    _TASKS[run_id] = task
    task.add_done_callback(lambda _: _TASKS.pop(run_id, None))

    logger.info("trading_desk_run_started", run_id=run_id, ticker=ticker, engine=engine.name)
    return run_id


async def _execute(
    redis: Redis,
    run_id: str,
    ticker: str,
    trade_date: str,
    engine: TradingEngine,
) -> None:
    """在后台执行一次运行，把引擎事件流包进统一的生命周期事件里。"""
    started_at = time.monotonic()
    descriptor = engine.describe()

    await event_bus.publish(
        redis,
        run_id,
        TradingDeskEvent.of(
            run_id,
            EventType.RUN_STARTED,
            RunStartedData(
                ticker=ticker,
                trade_date=trade_date,
                engine=descriptor.engine,
                capabilities=descriptor.capabilities,
                stages=descriptor.stages,
            ),
        ),
    )

    status: RunStatus = "completed"
    # 上一次观察到的暂停态，用于只在翻转时发 run.paused / run.resumed
    was_paused = False

    async def is_paused() -> bool:
        nonlocal was_paused
        paused = await tdc.is_paused(redis, run_id)
        if paused != was_paused:
            was_paused = paused
            await event_bus.publish(
                redis,
                run_id,
                TradingDeskEvent.of(run_id, EventType.RUN_PAUSED if paused else EventType.RUN_RESUMED),
            )
        return paused

    async def is_cancelled() -> bool:
        return await tdc.is_cancelled(redis, run_id)

    async def drain_notes() -> list[str]:
        return await tdc.drain_notes(redis, run_id)

    ctx = RunContext(
        run_id=run_id,
        ticker=ticker,
        trade_date=trade_date,
        control=ControlHandle(is_paused=is_paused, is_cancelled=is_cancelled, drain_notes=drain_notes),
    )

    try:
        async for event in engine.astream(ctx):
            await event_bus.publish(redis, run_id, event)

        if await tdc.is_cancelled(redis, run_id):
            status = "cancelled"
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:  # noqa: BLE001 —— 任何引擎异常都要变成前端可见的事件
        status = "failed"
        logger.exception("trading_desk_run_failed", run_id=run_id, ticker=ticker)
        await event_bus.publish(
            redis,
            run_id,
            TradingDeskEvent.of(run_id, EventType.ERROR, ErrorData(message=str(exc), fatal=True)),
        )
    finally:
        await event_bus.publish(
            redis,
            run_id,
            TradingDeskEvent.of(
                run_id,
                EventType.RUN_FINISHED,
                RunFinishedData(
                    status=status,
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                ),
            ),
        )
        await tdc.clear_control(redis, run_id)
        logger.info("trading_desk_run_finished", run_id=run_id, status=status)


async def pause(redis: Redis, run_id: str) -> None:
    """请求暂停。引擎在下一个节点边界停住。"""
    await tdc.set_paused(redis, run_id, True)


async def resume(redis: Redis, run_id: str) -> None:
    """解除暂停。"""
    await tdc.set_paused(redis, run_id, False)


async def cancel(redis: Redis, run_id: str) -> None:
    """请求取消。

    同时解除暂停：否则引擎会卡在暂停轮询里，永远走不到检查取消的那一步。
    """
    await tdc.set_cancelled(redis, run_id)
    await tdc.set_paused(redis, run_id, False)


async def inject(redis: Redis, run_id: str, text: str) -> None:
    """排入一条人工意见，引擎在下一个节点边界取走。"""
    await tdc.push_note(redis, run_id, text)


async def wait_for(run_id: str) -> None:
    """等待同进程内的运行结束。仅供测试与优雅关闭使用。"""
    task = _TASKS.get(run_id)
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)
