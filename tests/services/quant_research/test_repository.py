"""数据访问层：需要本地 Postgres（infra/docker-compose 的 postgres 服务 + make migrate）。连不上则跳过。"""

from datetime import date, datetime

import pytest

from app.services.quant_research import repository as repo

pytestmark = pytest.mark.slow
MARKET = "tst"


async def _db_available() -> bool:
    try:
        await repo.latest_distribution_date(MARKET)
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
async def clean(monkeypatch):
    # 全局连接池绑定在创建它的事件循环上，pytest 每个测试换一个循环 → 测试里改用无池会话
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.db.session import _PG_BASE

    engine = create_async_engine(f"postgresql+asyncpg://{_PG_BASE}", poolclass=NullPool)
    monkeypatch.setattr(repo, "AsyncSessionFactory", async_sessionmaker(engine, class_=AsyncSession,
                                                                        expire_on_commit=False))
    if not await _db_available():
        pytest.skip("本地 Postgres 不可用")
    await repo.delete_market(MARKET)
    yield
    await repo.delete_market(MARKET)
    await engine.dispose()


def _est(day, eps, fiscal="2027-01-25"):
    return {"market": MARKET, "symbol": "NVDA", "snapshot_date": day, "fiscal_date": fiscal, "eps_avg": eps,
            "eps_low": None, "eps_high": None, "revenue_avg": 1.0, "ebitda_avg": None, "ebit_avg": None,
            "n_analysts": 30}


async def test_estimates_insert_only_no_overwrite(clean):
    assert await repo.insert_estimates([_est(date(2026, 9, 30), 5.0)]) == 1
    assert await repo.insert_estimates([_est(date(2026, 9, 30), 9.9), _est(date(2026, 10, 1), 5.1)]) == 1
    hist = await repo.get_estimate_history(MARKET, ["NVDA"], date(2026, 1, 1))
    by_day = {p.snapshot_date: p.eps_avg for p in hist["NVDA"]}
    assert by_day == {date(2026, 9, 30): 5.0, date(2026, 10, 1): 5.1}
    assert await repo.earliest_estimate_date(MARKET) == date(2026, 9, 30)


async def test_fundamental_upsert(clean):
    await repo.upsert_fundamental(MARKET, "NVDA", [{"date": "2026-07-26", "filingDate": "2026-08-26 16:00"}], [], None)
    await repo.upsert_fundamental(MARKET, "NVDA", [{"date": "2026-10-26", "filingDate": "2026-11-20"}], [], {"a": 1})
    f = (await repo.get_fundamentals(MARKET))["NVDA"]
    assert f.latest_quarter_date == "2026-10-26" and f.filing_date == "2026-11-20" and f.balance == {"a": 1}


async def test_distributions_replace_and_results(clean):
    d = date(2026, 9, 30)
    await repo.replace_distributions(MARKET, d, {("tech", "pe_ttm"): [1.0, 2.0]})
    await repo.replace_distributions(MARKET, d, {("tech", "pe_ttm"): [3.0], ("_all", "_overall"): [50.0]})
    assert await repo.get_distributions(MARKET, d) == {("tech", "pe_ttm"): [3.0], ("_all", "_overall"): [50.0]}
    assert await repo.latest_distribution_date(MARKET) == d

    row = {"market": MARKET, "symbol": "NVDA", "sector_key": "tech", "payload_zh": {"x": 1}, "payload_en": {},
           "grades": {"overall": "A"}}
    await repo.upsert_results([dict(row, as_of=d)])
    await repo.upsert_results([dict(row, as_of=d, grades={"overall": "B"})])
    await repo.upsert_results([dict(row, as_of=date(2026, 10, 1), grades={"overall": "A-"})])
    latest = await repo.get_latest_result(MARKET, "NVDA")
    assert latest is not None and latest.as_of == date(2026, 10, 1)
    assert await repo.get_prev_grades(MARKET, date(2026, 10, 1)) == {"NVDA": {"overall": "B"}}


async def test_radar_grade_history_is_scoped_and_includes_last_stale_row(clean):
    """只取指定市场/股票，保留区间内每日等级及区间前最后一条供过期判断。"""
    base = {"market": MARKET, "sector_key": "tech", "payload_en": {}, "grades": {}}
    rows = []
    for symbol in ("NVDA", "OTHER"):
        for day, grade in ((1, "B"), (2, "A-"), (29, "A"), (30, "A+")):
            rows.append(dict(base, symbol=symbol, as_of=date(2026, 9, day),
                             payload_zh={"overall": {"grade": grade, "score": 70}, "dimensions": ["不读取"]}))
    await repo.upsert_results(rows)
    result = await repo.get_quant_grade_history(MARKET, ["NVDA"], date(2026, 9, 23), date(2026, 9, 29))
    assert [(r.symbol, r.as_of.day, r.payload_zh["overall"]["grade"]) for r in result] == [
        ("NVDA", 29, "A"), ("NVDA", 2, "A-")]
    assert all("dimensions" not in r.payload_zh for r in result)
    assert await repo.get_quant_grade_history("nonexistent", ["NVDA"], date(2026, 9, 1), date(2026, 9, 30)) == []
    assert await repo.get_quant_grade_history(MARKET, [], date(2026, 9, 1), date(2026, 9, 30)) == []


async def test_align_backfill_timestamps_marks_late_rows_at_batch_time(clean):
    """白天补跑写入的行（created_at 晚于 as_of 的定时跑批点）对齐回定时点，当时的雷达日即可用。"""
    from sqlalchemy import text

    from app.services.signal_radar import quant_filter

    payload = {"overall": {"grade": "A", "score": 70}, "as_of": {}}
    base = {"market": MARKET, "sector_key": "tech", "payload_zh": payload, "payload_en": {}, "grades": {}}
    await repo.upsert_results([dict(base, symbol="LATE", as_of=date(2026, 9, 29)),
                               dict(base, symbol="ONIT", as_of=date(2026, 9, 29))])
    # LATE = 次日 02:00 白天补跑；ONIT = 当晚 22:40 定时批，两种写入时刻都要可控
    async with repo.AsyncSessionFactory() as s:
        for sym, ts in (("LATE", datetime(2026, 9, 30, 2, 0)), ("ONIT", datetime(2026, 9, 29, 22, 40))):
            await s.execute(text("UPDATE quant_results SET created_at = :ts, updated_at = :ts "
                                 "WHERE market = :m AND symbol = :s"),
                            {"ts": ts, "m": MARKET, "s": sym})
        await s.commit()

    async def history_of() -> dict:
        rows = await repo.get_quant_grade_history(MARKET, ["LATE", "ONIT"], date(2026, 9, 29), date(2026, 9, 29))
        out = {}
        for r in rows:
            entry = quant_filter.grade_from_row(r)
            out[r.symbol] = [entry] if entry else []
        return out

    # 对齐前：补跑行的可用日被写入时刻卡住，昨天的雷达日看不到
    assert quant_filter.grade_on(await history_of(), "LATE", date(2026, 9, 29))[1] == "missing"

    assert await repo.align_backfill_timestamps(MARKET, 22, 30) == 1
    assert await repo.align_backfill_timestamps(MARKET, 22, 30) == 0  # 幂等

    rows = await repo.get_quant_grade_history(MARKET, ["LATE", "ONIT"], date(2026, 9, 29), date(2026, 9, 29))
    stamps = {r.symbol: r.created_at for r in rows}
    assert stamps["LATE"] == datetime(2026, 9, 29, 22, 30)
    assert stamps["ONIT"] == datetime(2026, 9, 29, 22, 40)  # 正常写入不动
    assert quant_filter.grade_on(await history_of(), "LATE", date(2026, 9, 29))[1] == "eligible"
    assert quant_filter.grade_on(await history_of(), "ONIT", date(2026, 9, 29))[1] == "eligible"
