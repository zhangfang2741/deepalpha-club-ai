"""量化研究四张表的数据访问（异步）。

预期快照只补不覆盖（ON CONFLICT DO NOTHING），保证存档是当时可见的数据；
报表快照与每日结果按唯一键 upsert；板块分布按 (market, as_of) 整体替换。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from app.db.session import AsyncSessionFactory
from app.models.quant_research import (
    QuantEstimateSnapshot,
    QuantFundamentalSnapshot,
    QuantResult,
    QuantSectorDistribution,
)
from app.services.quant_research.revisions import EstimatePoint
from app.services.quant_research.scoring import Distributions

_CHUNK = 500


def _chunks(rows: list, n: int = _CHUNK) -> Iterable[list]:
    for i in range(0, len(rows), n):
        yield rows[i: i + n]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------- 报表快照 ----------

async def upsert_fundamental(market: str, symbol: str, income: list, cash: list, balance: dict | None) -> None:
    """写入 / 更新一只股票的报表快照。"""
    latest = income[0] if income else {}
    values = {
        "market": market, "symbol": symbol,
        "latest_quarter_date": latest.get("date"), "filing_date": (latest.get("filingDate") or "")[:10] or None,
        "income_quarters": income, "cash_quarters": cash, "balance": balance, "fetched_at": _now(),
        # 表的时间列不带时区；基类默认值是带时区的 now(UTC)，Core 插入会用上它 → 显式给 naive UTC
        "created_at": _now(), "updated_at": _now(),
    }
    stmt = insert(QuantFundamentalSnapshot).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_quant_fundamental",
        set_={k: stmt.excluded[k] for k in ("latest_quarter_date", "filing_date", "income_quarters",
                                            "cash_quarters", "balance", "fetched_at", "updated_at")},
    )
    async with AsyncSessionFactory() as s:
        await s.execute(stmt)
        await s.commit()


async def get_fundamentals(market: str, symbols: list[str] | None = None) -> dict[str, QuantFundamentalSnapshot]:
    """读取报表快照 {symbol: 行}。"""
    q = select(QuantFundamentalSnapshot).where(col(QuantFundamentalSnapshot.market) == market)
    if symbols is not None:
        q = q.where(col(QuantFundamentalSnapshot.symbol).in_(symbols))
    async with AsyncSessionFactory() as s:
        rows = (await s.execute(q)).scalars().all()
    return {r.symbol: r for r in rows}


# ---------- 一致预期快照 ----------

async def insert_estimates(rows: list[dict]) -> int:
    """批量写入一致预期快照，已存在的 (market, symbol, snapshot_date, fiscal_date) 不覆盖。

    rows 字段：market, symbol, snapshot_date, fiscal_date, eps_avg, eps_low, eps_high, revenue_avg,
    ebitda_avg, ebit_avg, n_analysts。
    """
    if not rows:
        return 0
    now = _now()
    inserted = 0
    async with AsyncSessionFactory() as s:
        for chunk in _chunks(rows):
            payload = [dict(r, created_at=now, updated_at=now) for r in chunk]
            stmt = insert(QuantEstimateSnapshot).values(payload).on_conflict_do_nothing(constraint="uq_quant_estimate")
            res = await s.execute(stmt)
            inserted += res.rowcount or 0  # type: ignore[attr-defined]
        await s.commit()
    return inserted


async def get_estimate_history(market: str, symbols: list[str], since: date) -> dict[str, list[EstimatePoint]]:
    """读取 since 之后的一致预期快照，按股票分组。"""
    q = (select(QuantEstimateSnapshot)
         .where(col(QuantEstimateSnapshot.market) == market,
                col(QuantEstimateSnapshot.symbol).in_(symbols),
                col(QuantEstimateSnapshot.snapshot_date) >= since))
    out: dict[str, list[EstimatePoint]] = {s: [] for s in symbols}
    async with AsyncSessionFactory() as s:
        for r in (await s.execute(q)).scalars():
            out.setdefault(r.symbol, []).append(
                EstimatePoint(r.snapshot_date, r.fiscal_date, r.eps_avg, r.revenue_avg, r.n_analysts))
    return out


async def earliest_estimate_date(market: str) -> date | None:
    """最早一份预期快照的日期。"""
    async with AsyncSessionFactory() as s:
        return (await s.execute(
            select(func.min(col(QuantEstimateSnapshot.snapshot_date))).where(col(QuantEstimateSnapshot.market) == market)
        )).scalar()


# ---------- 板块分布 ----------

async def replace_distributions(market: str, as_of: date, dists: Distributions) -> None:
    """整体替换某日的板块分布。"""
    now = _now()
    async with AsyncSessionFactory() as s:
        await s.execute(delete(QuantSectorDistribution).where(
            col(QuantSectorDistribution.market) == market, col(QuantSectorDistribution.as_of) == as_of))
        rows = [{"market": market, "as_of": as_of, "sector_key": sector, "metric_key": metric, "values": values,
                 "created_at": now, "updated_at": now} for (sector, metric), values in dists.items()]
        for chunk in _chunks(rows):
            await s.execute(insert(QuantSectorDistribution).values(chunk))
        await s.commit()


async def latest_distribution_date(market: str) -> date | None:
    """最近一次批量的日期。"""
    async with AsyncSessionFactory() as s:
        return (await s.execute(
            select(func.max(col(QuantSectorDistribution.as_of))).where(col(QuantSectorDistribution.market) == market)
        )).scalar()


async def get_distributions(market: str, as_of: date) -> Distributions:
    """读取某日的全部板块分布。"""
    q = select(QuantSectorDistribution).where(col(QuantSectorDistribution.market) == market,
                                              col(QuantSectorDistribution.as_of) == as_of)
    async with AsyncSessionFactory() as s:
        return {(r.sector_key, r.metric_key): list(r.values) for r in (await s.execute(q)).scalars()}


# ---------- 每日结果 ----------

async def upsert_results(rows: list[dict]) -> None:
    """rows: market, symbol, as_of, sector_key, payload_zh, payload_en, grades。"""
    if not rows:
        return
    now = _now()
    async with AsyncSessionFactory() as s:
        for chunk in _chunks(rows, 200):
            stmt = insert(QuantResult).values([dict(r, created_at=now, updated_at=now) for r in chunk])
            stmt = stmt.on_conflict_do_update(
                constraint="uq_quant_result",
                set_={k: stmt.excluded[k] for k in ("sector_key", "payload_zh", "payload_en", "grades", "updated_at")},
            )
            await s.execute(stmt)
        await s.commit()


@dataclass(frozen=True)
class QuantGradeSnapshot:
    """雷达只读取综合评级和数据日期，避免拉取全部指标明细。"""

    symbol: str
    as_of: date
    created_at: datetime
    updated_at: datetime
    payload_zh: dict
    payload_en: dict


async def get_quant_grade_history(market: str, symbols: list[str], start: date, end: date) -> list[QuantGradeSnapshot]:
    """按市场和评级日期批量读取；可用时间校验由雷达筛选层完成。"""
    if not symbols:
        return []
    previous = (select(col(QuantResult.id))
                .where(col(QuantResult.market) == market, col(QuantResult.symbol).in_(symbols),
                       col(QuantResult.as_of) < start)
                .distinct(col(QuantResult.symbol))
                .order_by(col(QuantResult.symbol), col(QuantResult.as_of).desc()))
    q = (select(col(QuantResult.symbol), col(QuantResult.as_of),
                col(QuantResult.created_at), col(QuantResult.updated_at),
                col(QuantResult.payload_zh)["overall"], col(QuantResult.payload_zh)["as_of"],
                col(QuantResult.payload_en)["overall"], col(QuantResult.payload_en)["as_of"])
         .where(col(QuantResult.market) == market,
                col(QuantResult.symbol).in_(symbols), col(QuantResult.as_of) <= end,
                or_(col(QuantResult.as_of) >= start, col(QuantResult.id).in_(previous)))
         .order_by(col(QuantResult.as_of).desc(), col(QuantResult.updated_at).desc()))
    async with AsyncSessionFactory() as session:
        rows = (await session.execute(q)).all()
    return [QuantGradeSnapshot(symbol, as_of, created, updated,
                              {"overall": zh, "as_of": zh_dates} if zh else {},
                              {"overall": en, "as_of": en_dates} if en else {})
            for symbol, as_of, created, updated, zh, zh_dates, en, en_dates in rows]


async def get_latest_result(market: str, symbol: str) -> QuantResult | None:
    """某只股票最近一天的结果。"""
    q = (select(QuantResult).where(col(QuantResult.market) == market, col(QuantResult.symbol) == symbol)
         .order_by(col(QuantResult.as_of).desc()).limit(1))
    async with AsyncSessionFactory() as s:
        return (await s.execute(q)).scalars().first()


async def get_prev_grades(market: str, before: date) -> dict[str, dict]:
    """取 before 之前最近一个交易日每只股票的等级（防抖用）。"""
    async with AsyncSessionFactory() as s:
        prev = (await s.execute(select(func.max(col(QuantResult.as_of))).where(
            col(QuantResult.market) == market, col(QuantResult.as_of) < before))).scalar()
        if prev is None:
            return {}
        rows = (await s.execute(select(col(QuantResult.symbol), col(QuantResult.grades)).where(
            col(QuantResult.market) == market, col(QuantResult.as_of) == prev))).all()
    return {sym: grades for sym, grades in rows}


async def delete_market(market: str) -> None:
    """测试用：清掉某个 market 的全部数据。"""
    async with AsyncSessionFactory() as s:
        for model in (QuantEstimateSnapshot, QuantFundamentalSnapshot, QuantResult, QuantSectorDistribution):
            await s.execute(delete(model).where(col(model.market) == market))
        await s.commit()
