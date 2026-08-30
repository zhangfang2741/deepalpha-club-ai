"""TradingDeskRun 表的读写。

落库策略：
  - run 开始时 init_run() 写一行 status="running" 的占位（让前端历史列表
    立即能看到在跑的那条，避免「运行中空白」）。
  - run 结束时 finalize_run() 用 status / verdict / signals / turns /
    duration_ms / finished_at 全量更新该行。idempotent：重复调只覆盖不抛。
  - 列表 / 详情查询只走表，不走 Redis Stream。Redis 留给断线续读与重放；
    历史页要的 turn 级全文 / 信号序列已经在表里。

为什么不走 Redis：Redis Stream 7 天后自动过期（settings.TRADING_DESK_EVENT_TTL_SECONDS），
而历史 run 用户希望能翻很久。Postgres 表是事实来源。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.trading_desk_run import TradingDeskRun


async def init_run(
    db: AsyncSession,
    *,
    run_id: str,
    user_id: int,
    ticker: str,
    trade_date: str,
    engine: str,
) -> None:
    """插入一行 status=running 的占位记录。

    与 start_run 同步发出 run.started 的时序策略一致：插入尽早完成，
    让任何读历史列表的请求都不会撞到「run 在跑但表里查不到」的竞态。
    """
    row = TradingDeskRun(
        id=run_id,
        user_id=user_id,
        ticker=ticker,
        trade_date=trade_date,
        engine=engine,
        status="running",
        verdict=None,
        signals=None,
        turns=None,
        duration_ms=0,
        finished_at=None,
    )
    db.add(row)
    await db.commit()


async def finalize_run(
    db: AsyncSession,
    *,
    run_id: str,
    status: str,
    duration_ms: int,
    verdict: dict[str, Any] | None,
    signals: list[dict[str, Any]] | None,
    turns: list[dict[str, Any]] | None,
) -> None:
    """收尾更新该 run 的结构化字段。

    runner 在 finally 块调；行不存在时静默跳过（init_run 失败意味着
    整次运行没起来，再 finalize 也没意义）。
    """
    row = await db.get(TradingDeskRun, run_id)
    if row is None:
        return
    row.status = status
    row.duration_ms = duration_ms
    row.verdict = verdict
    row.signals = signals
    row.turns = turns
    row.finished_at = datetime.now(UTC)
    db.add(row)
    await db.commit()


async def list_runs(
    db: AsyncSession,
    *,
    user_id: int,
    ticker: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[TradingDeskRun]:
    """列某用户的最近 run；可按 ticker 过滤。

    排序：finished_at 倒序优先（已完成的最新在上），未完成时退回
    created_at 倒序（运行中的最新在上）。
    """
    stmt = select(TradingDeskRun).where(TradingDeskRun.user_id == user_id)
    if ticker:
        stmt = stmt.where(TradingDeskRun.ticker == ticker.upper())
    # finished_at desc NULLS LAST, then created_at desc
    stmt = stmt.order_by(  # type: ignore[arg-type]
        TradingDeskRun.finished_at.desc().nulls_last(),  # type: ignore[union-attr]
        TradingDeskRun.created_at.desc(),
    ).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_run(db: AsyncSession, *, run_id: str, user_id: int) -> TradingDeskRun | None:
    """取一条 run；user_id 不匹配返回 None（越权检查与 404 走同一路径）。"""
    row = await db.get(TradingDeskRun, run_id)
    if row is None or row.user_id != user_id:
        return None
    return row


# ── 同步版（Celery / 测试 fixture 用）──────────────────────────────────


def init_run_sync(
    db: Session,
    *,
    run_id: str,
    user_id: int,
    ticker: str,
    trade_date: str,
    engine: str,
) -> None:
    """同步 init_run。"""
    row = TradingDeskRun(
        id=run_id,
        user_id=user_id,
        ticker=ticker,
        trade_date=trade_date,
        engine=engine,
        status="running",
    )
    db.add(row)
    db.commit()


def finalize_run_sync(
    db: Session,
    *,
    run_id: str,
    status: str,
    duration_ms: int,
    verdict: dict[str, Any] | None,
    signals: list[dict[str, Any]] | None,
    turns: list[dict[str, Any]] | None,
) -> None:
    """同步 finalize_run。"""
    row = db.get(TradingDeskRun, run_id)
    if row is None:
        return
    row.status = status
    row.duration_ms = duration_ms
    row.verdict = verdict
    row.signals = signals
    row.turns = turns
    row.finished_at = datetime.now(UTC)
    db.add(row)
    db.commit()