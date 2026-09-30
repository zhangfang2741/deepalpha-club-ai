"""数据访问层：需要本地 Postgres（infra/docker-compose 的 postgres 服务 + make migrate）。连不上则跳过。"""

from datetime import date

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
