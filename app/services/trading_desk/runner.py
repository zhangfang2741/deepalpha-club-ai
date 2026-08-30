"""交易台运行编排。

职责边界：
  - runner 负责生命周期（run.started / run.finished / error）与控制信号，
    引擎只负责产出中间事件。这样所有引擎的生命周期语义一致，前端不必
    为每个引擎写特例。
  - 运行跑在后台 asyncio 任务里，HTTP 请求立即返回 run_id；SSE 端点是
    独立的消费者，断开不影响运行。
  - 收尾时把整次事件流折叠成 (verdict, signals, turns) 落 TradingDeskRun
    表（plan §6 持久化层）。Redis Stream 留给断线续读与重放；历史列表 /
    详情只查表，避免依赖短 TTL 的缓存。

已知取舍：web 进程重启会中断在跑的 run（spec §11）。研究工具可接受，
且事件流已落 Redis，partial 结果仍可见。进程崩溃导致 _execute 没跑到
finally 时，占位行会留在 status="running" —— 历史列表单独标出来即可。
"""

from __future__ import annotations

import asyncio
import time
import uuid

from redis.asyncio import Redis

from app.cache import trading_desk_cache as tdc
from app.core.logging import logger
from app.db.session import AsyncSessionFactory
from app.schemas.trading_desk import (
    ErrorData,
    EventType,
    RunFinishedData,
    RunStartedData,
    TradingDeskEvent,
)
from app.services.trading_desk import event_bus, persistence, summariser
from app.services.trading_desk.engine_base import ControlHandle, RunContext, TradingEngine

# run_id -> 后台任务。仅用于同进程内的 wait_for / 观测；
# 控制信号一律走 Redis，不依赖这个字典（进程重启后它会空掉）。
_TASKS: dict[str, asyncio.Task[None]] = {}

# 进程级 DB 会话工厂：默认走 AsyncSessionFactory，测试用 monkeypatch 替换。
# 这样 runner 的 start_run / _execute 不被 caller 的 session 生命周期绑死。
SessionFactory = AsyncSessionFactory


async def start_run(
    redis: Redis,
    *,
    user_id: int,
    ticker: str,
    trade_date: str,
    engine: TradingEngine,
) -> str:
    """创建一次运行并立即返回 run_id，实际执行在后台进行。

    三件同步事：
      1. 初始化 Redis 控制位
      2. 同步发出 run.started —— 否则调用方拿到 run_id 后立刻订阅会撞上
         「事件流尚不存在」的竞态
      3. 同步写入 status=running 的占位行 —— 否则历史列表请求会比
         run.started 早到，看到「这个 run 不存在」
    """
    run_id = uuid.uuid4().hex
    await tdc.init_control(redis, run_id)

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
    try:
        async with SessionFactory() as db:
            await persistence.init_run(
                db,
                run_id=run_id,
                user_id=user_id,
                ticker=ticker,
                trade_date=trade_date,
                engine=descriptor.engine,
            )
    except Exception:
        # 落库失败：把 run_id 上面的流清掉，避免留下一个永远空跑的幽灵 run。
        logger.exception("trading_desk_init_persist_failed", run_id=run_id)
        await tdc.clear_control(redis, run_id)
        raise

    task = asyncio.create_task(_execute(redis, run_id, ticker, trade_date, engine, user_id))
    _TASKS[run_id] = task
    task.add_done_callback(lambda _: _TASKS.pop(run_id, None))

    logger.info(
        "trading_desk_run_started", run_id=run_id, ticker=ticker,
        engine=engine.name, user_id=user_id,
    )
    return run_id


async def _execute(
    redis: Redis,
    run_id: str,
    ticker: str,
    trade_date: str,
    engine: TradingEngine,
    user_id: int,
) -> None:
    """在后台执行一次运行。

    收集所有引擎事件用于收尾折叠（verdict / signals / turns）。事件本身
    早已通过 event_bus.publish 写到 Redis Stream，in-memory 列表只是
    本进程 fast-path。
    """
    started_at = time.monotonic()
    status = "completed"
    events: list[TradingDeskEvent] = []
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
            events.append(event)
            await event_bus.publish(redis, run_id, event)

        if await tdc.is_cancelled(redis, run_id):
            status = "cancelled"
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:  # noqa: BLE001 —— 任何引擎异常都要变成前端可见的事件
        status = "failed"
        logger.exception("trading_desk_run_failed", run_id=run_id, ticker=ticker)
        fatal_event = TradingDeskEvent.of(
            run_id, EventType.ERROR, ErrorData(message=str(exc), fatal=True),
        )
        events.append(fatal_event)
        await event_bus.publish(redis, run_id, fatal_event)
    finally:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        finished_event = TradingDeskEvent.of(
            run_id,
            EventType.RUN_FINISHED,
            RunFinishedData(status=status, duration_ms=duration_ms),
        )
        events.append(finished_event)
        # finally 段四件事分头 try：保证 RUN_FINISHED 一定先发出去，
        # 然后清控制位、落库各走各路。一处失败不应牵连其它步骤。
        try:
            await event_bus.publish(redis, run_id, finished_event)
        except Exception:
            logger.exception(
                "trading_desk_publish_finished_failed",
                run_id=run_id, status=status,
            )
        try:
            await tdc.clear_control(redis, run_id)
        except Exception:
            logger.exception(
                "trading_desk_clear_control_failed",
                run_id=run_id, status=status,
            )

        # 落库：摘要 + 状态。落库失败不应让前端看不见 RUN_FINISHED —— log 后继续。
        verdict, signals, turns = summariser.summarise(events)
        try:
            async with SessionFactory() as db:
                await persistence.finalize_run(
                    db,
                    run_id=run_id,
                    status=status,
                    duration_ms=duration_ms,
                    verdict=verdict,
                    signals=signals,
                    turns=turns,
                )
        except Exception:
            logger.exception("trading_desk_persist_failed", run_id=run_id, status=status)

        logger.info(
            "trading_desk_run_finished", run_id=run_id, status=status,
            duration_ms=duration_ms, user_id=user_id,
        )


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