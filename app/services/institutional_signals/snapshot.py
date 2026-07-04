"""每日快照持久化：写入当日、读取历史。

写入为 best-effort——DB 不可用时由调用方吞掉异常，不影响信号报告。
"""
import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal_snapshot import SignalSnapshot

# 快照可写入的度量字段
_METRIC_FIELDS = (
    "eps_estimate", "revenue_estimate", "price_target_avg",
    "call_oi", "put_oi", "call_vol", "put_vol", "atm_iv",
)


async def upsert_snapshot(session: AsyncSession, symbol: str, snapshot_date: str, metrics: dict) -> None:
    """写入/更新某标的某日快照（symbol + snapshot_date 唯一）。"""
    # 列为 TIMESTAMP WITHOUT TIME ZONE，用 naive UTC 避免 asyncpg 类型冲突
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    clean = {k: metrics.get(k) for k in _METRIC_FIELDS}
    stmt = pg_insert(SignalSnapshot).values(
        id=uuid.uuid4(), created_at=now, updated_at=now,
        symbol=symbol, snapshot_date=snapshot_date, **clean,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_signal_snapshot",
        set_={**clean, "updated_at": now},
    )
    await session.execute(stmt)
    await session.commit()


async def get_snapshot_history(session: AsyncSession, symbol: str, days: int) -> list[SignalSnapshot]:
    """读取最近 days 天的历史快照，按日期升序。"""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    stmt = (
        select(SignalSnapshot)
        .where(SignalSnapshot.symbol == symbol, SignalSnapshot.snapshot_date >= cutoff)
        .order_by(SignalSnapshot.snapshot_date)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
