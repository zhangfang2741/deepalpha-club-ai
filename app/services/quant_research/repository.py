"""量化研究四张表的数据访问（异步）。

预期快照只补不覆盖（ON CONFLICT DO NOTHING），保证存档是当时可见的数据；
报表快照与每日结果按唯一键 upsert；板块分布按 (market, as_of) 整体替换。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from app.db.session import AsyncSessionFactory
from app.models.quant_research import (
    QuantEstimateSnapshot,
    QuantFundamentalSnapshot,
    QuantMoatAssessment,
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


async def upsert_raw_reports(market: str, rows: list[dict]) -> int:
    """A 股 / 港股：批量写入累计口径原始报告（rows：symbol, reports, balance）。

    与美股共用 quant_fundamental_snapshots：income_quarters 存累计报告（cnhk/reports.py 的格式，新 → 旧），
    cash_quarters 留空，balance 存最新资产负债表；读取时再换算成单季。
    """
    now = _now()
    values = []
    for r in rows:
        reps = r["reports"]
        latest = reps[0] if reps else {}
        values.append({
            "market": market, "symbol": r["symbol"], "latest_quarter_date": latest.get("report_date"),
            "filing_date": latest.get("notice_date"), "income_quarters": reps, "cash_quarters": [],
            "balance": r.get("balance"), "fetched_at": now, "created_at": now, "updated_at": now,
        })
    async with AsyncSessionFactory() as s:
        for chunk in _chunks(values, 200):
            stmt = insert(QuantFundamentalSnapshot).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_quant_fundamental",
                set_={k: stmt.excluded[k] for k in ("latest_quarter_date", "filing_date", "income_quarters",
                                                    "cash_quarters", "balance", "fetched_at", "updated_at")},
            )
            await s.execute(stmt)
        await s.commit()
    return len(values)


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


async def latest_methodology_version(market: str) -> str | None:
    """最近一次批量结果的方法版本（取任一行 payload 里的 methodology_version）。"""
    async with AsyncSessionFactory() as s:
        latest = (await s.execute(
            select(func.max(col(QuantResult.as_of))).where(col(QuantResult.market) == market))).scalar()
        if latest is None:
            return None
        payload = (await s.execute(
            select(col(QuantResult.payload_zh)).where(col(QuantResult.market) == market,
                                                 col(QuantResult.as_of) == latest).limit(1))).scalar()
    return (payload or {}).get("methodology_version")


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
    """雷达只读取综合评级、数据日期和排雷用的维度等级，避免拉取全部指标明细。"""

    symbol: str
    as_of: date
    created_at: datetime
    updated_at: datetime
    payload_zh: dict
    payload_en: dict
    # 与 QuantResult.grades 同键（d:<维度>），只含 RADAR_DIMENSION_KEYS
    grades: dict = field(default_factory=dict)
    # 评级方法版本（payload 里的 methodology_version）：评级升降事件不跨方法版本比较
    methodology: str | None = None


# 雷达基本面排雷读取的维度等级（grades 列的键）
RADAR_DIMENSION_KEYS = ("d:profitability", "d:revisions")


async def align_backfill_timestamps(market: str, hour: int, minute: int) -> int:
    """把补跑写入的行对齐回该评级日的定时跑批时刻，返回改动行数。

    自举/故障重试在白天补跑时 created_at 落在 as_of 次日，雷达的可用日判断
    （available_on 含写入时刻）会让这批评级对当时的展示日永远不可见。补跑的
    语义是「补上当时本应发生的跑批」，时间戳应标定时点。以「写入日晚于评级日」
    为补跑标志：当晚定时批（22:31~23:59 陆续写入，日期仍等于 as_of）不动。
    幂等，可重复执行。
    """
    q = text("""
        UPDATE quant_results
        SET created_at = as_of + make_interval(hours => :hour, mins => :minute),
            updated_at = as_of + make_interval(hours => :hour, mins => :minute)
        WHERE market = :market
          AND created_at::date > as_of
    """)
    async with AsyncSessionFactory() as s:
        res = await s.execute(q, {"market": market, "hour": hour, "minute": minute})
        await s.commit()
        return res.rowcount or 0


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
                col(QuantResult.payload_zh)["methodology_version"].as_string(),
                col(QuantResult.payload_en)["overall"], col(QuantResult.payload_en)["as_of"],
                *(col(QuantResult.grades)[k] for k in RADAR_DIMENSION_KEYS))
         .where(col(QuantResult.market) == market,
                col(QuantResult.symbol).in_(symbols), col(QuantResult.as_of) <= end,
                or_(col(QuantResult.as_of) >= start, col(QuantResult.id).in_(previous)))
         .order_by(col(QuantResult.as_of).desc(), col(QuantResult.updated_at).desc()))
    async with AsyncSessionFactory() as session:
        rows = (await session.execute(q)).all()
    return _grade_snapshots(rows)


def _grade_snapshots(rows) -> list[QuantGradeSnapshot]:
    return [QuantGradeSnapshot(symbol, as_of, created, updated,
                              {"overall": zh, "as_of": zh_dates} if zh else {},
                              {"overall": en, "as_of": en_dates} if en else {},
                              {k: v for k, v in zip(RADAR_DIMENSION_KEYS, dims, strict=True) if v},
                              version)
            for symbol, as_of, created, updated, zh, zh_dates, version, en, en_dates, *dims in rows]


async def get_dimension_scores(
    market: str, pairs: list[tuple[str, date]],
) -> dict[tuple[str, date], dict[str, float]]:
    """(评级表代码, 评级日) → {维度: 分数}，只含状态 ok 且计入综合的维度。

    雷达的评级历史查询故意不取维度明细（payload 很大）；只有「去动量」好股票口径需要，这里只展开
    dimensions 数组里的 key / score，不拉指标明细。
    """
    if not pairs:
        return {}
    wanted = set(pairs)
    q = text("""
        SELECT r.symbol, r.as_of, d->>'key', d->>'score'
        FROM quant_results r,
             jsonb_array_elements(r.payload_zh::jsonb->'dimensions') d
        WHERE r.market = :market
          AND r.symbol = ANY(:symbols)
          AND r.as_of >= :start AND r.as_of <= :end
          AND d->>'status' = 'ok'
          AND COALESCE(d->>'counts_in_overall', 'true') <> 'false'
          AND d->>'score' IS NOT NULL
    """)
    params = {"market": market, "symbols": sorted({s for s, _ in pairs}),
              "start": min(a for _, a in pairs), "end": max(a for _, a in pairs)}
    async with AsyncSessionFactory() as s:
        rows = (await s.execute(q, params)).all()
    out: dict[tuple[str, date], dict[str, float]] = {}
    for symbol, as_of, key, score in rows:
        if (symbol, as_of) in wanted:
            out.setdefault((symbol, as_of), {})[key] = float(score)
    return out


async def get_latest_quant_grades(market: str, symbols: list[str], start: date, end: date) -> list[QuantGradeSnapshot]:
    """每只股票在 [start, end] 内最新的一行评级（DISTINCT ON，一只一行）。

    只要「当前等级」的场景（好股票门槛 / 名单）用它：get_quant_grade_history 要把窗口内每天的行都读出来
    （500 只 × 十几天，逐行解 JSON），标普 500 要十几秒；这里一只一行，快一个数量级。
    """
    if not symbols:
        return []
    q = (select(col(QuantResult.symbol), col(QuantResult.as_of),
                col(QuantResult.created_at), col(QuantResult.updated_at),
                col(QuantResult.payload_zh)["overall"], col(QuantResult.payload_zh)["as_of"],
                col(QuantResult.payload_zh)["methodology_version"].as_string(),
                col(QuantResult.payload_en)["overall"], col(QuantResult.payload_en)["as_of"],
                *(col(QuantResult.grades)[k] for k in RADAR_DIMENSION_KEYS))
         .where(col(QuantResult.market) == market, col(QuantResult.symbol).in_(symbols),
                col(QuantResult.as_of) >= start, col(QuantResult.as_of) <= end)
         .distinct(col(QuantResult.symbol))
         .order_by(col(QuantResult.symbol), col(QuantResult.as_of).desc(), col(QuantResult.updated_at).desc()))
    async with AsyncSessionFactory() as session:
        rows = (await session.execute(q)).all()
    return _grade_snapshots(rows)


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


# ---------- 护城河 ----------

async def moat_assessed(market: str, method_version: str) -> dict[str, set[str]]:
    """已评估过的 {股票: {10-K 编号}}（当前方法版本），用于跳过已评估的年报。"""
    q = select(col(QuantMoatAssessment.symbol), col(QuantMoatAssessment.accession)).where(
        col(QuantMoatAssessment.market) == market, col(QuantMoatAssessment.method_version) == method_version)
    out: dict[str, set[str]] = {}
    async with AsyncSessionFactory() as s:
        for sym, acc in (await s.execute(q)).all():
            out.setdefault(sym, set()).add(acc)
    return out


async def insert_moat(row: dict) -> bool:
    """写入一份护城河评估；同一 (股票, 10-K, 方法版本) 已存在则不覆盖（point-in-time）。"""
    now = _now()
    stmt = insert(QuantMoatAssessment).values(dict(row, created_at=now, updated_at=now)) \
        .on_conflict_do_nothing(constraint="uq_quant_moat")
    async with AsyncSessionFactory() as s:
        res = await s.execute(stmt)
        await s.commit()
    return bool(res.rowcount)  # type: ignore[attr-defined]


async def latest_moat(market: str, symbol: str, method_version: str) -> QuantMoatAssessment | None:
    """该股最近一份年报的护城河评估。"""
    q = (select(QuantMoatAssessment)
         .where(col(QuantMoatAssessment.market) == market, col(QuantMoatAssessment.symbol) == symbol,
                col(QuantMoatAssessment.method_version) == method_version)
         .order_by(col(QuantMoatAssessment.filed_date).desc(), col(QuantMoatAssessment.assessed_at).desc())
         .limit(1))
    async with AsyncSessionFactory() as s:
        return (await s.execute(q)).scalars().first()


# ---------- 上线诊断（只读汇总用，见 diagnostics.py） ----------

async def diagnostic_dates(market: str, limit: int = 6) -> list[tuple[date, str | None, int]]:
    """最近几天有结果的日期（新 → 旧）：(as_of, 方法版本, 行数)。版本取当天任一行 payload 里的 methodology_version。"""
    async with AsyncSessionFactory() as s:
        days = (await s.execute(
            select(col(QuantResult.as_of), func.count()).where(col(QuantResult.market) == market)
            .group_by(col(QuantResult.as_of)).order_by(col(QuantResult.as_of).desc()).limit(limit))).all()
        out = []
        for as_of, n in days:
            ver = (await s.execute(
                select(col(QuantResult.payload_zh)["methodology_version"].as_string())
                .where(col(QuantResult.market) == market, col(QuantResult.as_of) == as_of).limit(1))).scalar()
            out.append((as_of, ver, n))
    return out


def _num_or_none(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


async def diagnostic_rows(market: str, as_of: date) -> list:
    """某天全部结果的诊断行：只取等级 / 阶段 / 综合分 / 各维度等级几个 JSON 字段，不拉指标明细。"""
    from app.services.quant_research.diagnostics import DiagRow  # 避免模块级循环依赖

    q = (select(col(QuantResult.symbol), col(QuantResult.grades),
                col(QuantResult.payload_zh)["overall"], col(QuantResult.payload_zh)["stage"],
                col(QuantResult.payload_zh)["methodology_version"].as_string())
         .where(col(QuantResult.market) == market, col(QuantResult.as_of) == as_of))
    async with AsyncSessionFactory() as s:
        rows = (await s.execute(q)).all()
    out = []
    for symbol, grades, overall, stage, version in rows:
        overall = overall if isinstance(overall, dict) else {}
        grades = grades if isinstance(grades, dict) else {}
        score, pct = overall.get("score"), overall.get("universe_percentile")
        out.append(DiagRow(
            symbol, version, overall.get("grade"),
            float(score) if isinstance(score, (int, float)) else None,
            float(pct) if isinstance(pct, (int, float)) else None,
            bool(overall.get("capped")), stage.get("key") if isinstance(stage, dict) else None,
            {k[2:]: v for k, v in grades.items() if k.startswith("d:")},
            _num_or_none(stage.get("revenue_growth_pct")) if isinstance(stage, dict) else None,
            _num_or_none(stage.get("revenue_cagr_3y_pct")) if isinstance(stage, dict) else None))
    return out
