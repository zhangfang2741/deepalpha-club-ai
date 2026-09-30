"""夜间批量编排：假 FMP + 内存版数据访问，25 只克隆股票（同板块，股价不同）跑全流程。"""

from datetime import date

import pytest

from app.services.quant_research import batch
from tests.services.quant_research.fixtures import raw

AS_OF = date(2026, 9, 30)
SYMS = [f"T{i:02d}" for i in range(25)]


class FakeFmp:
    def __init__(self, fail_price=()):
        self.calls: list[str] = []
        self.fail_price = set(fail_price)

    async def earnings_calendar(self, start, end):
        self.calls.append("calendar")
        return [{"symbol": "T01", "epsActual": 1.0}]

    async def income_quarters(self, s):
        self.calls.append(f"income:{s}")
        return raw("NVDA", "isq")

    async def cash_quarters(self, s):
        return raw("NVDA", "cfq")

    async def balance_latest(self, s):
        return raw("NVDA", "bsq")

    async def estimates_annual(self, s):
        return raw("NVDA", "est")

    async def price_light(self, s, as_of):
        if s in self.fail_price:
            return None
        k = 1 + int(s[1:]) / 10
        return [dict(p, price=p["price"] * k) for p in raw("NVDA", "px")]


class MemRepo:
    def __init__(self):
        self.fund, self.est, self.dists, self.results = {}, [], {}, []

    async def get_fundamentals(self, market, symbols=None):
        return {}

    async def upsert_fundamental(self, market, symbol, income, cash, balance):
        self.fund[symbol] = (income, cash, balance)

    async def insert_estimates(self, rows):
        self.est.extend(rows)
        return len(rows)

    async def get_estimate_history(self, market, symbols, since):
        return {s: [] for s in symbols}

    async def get_prev_grades(self, market, before):
        return {}

    async def replace_distributions(self, market, as_of, dists):
        self.dists = dists

    async def upsert_results(self, rows):
        self.results.extend(rows)


@pytest.fixture
def env(monkeypatch):
    mem, fake = MemRepo(), FakeFmp(fail_price={"T03"})
    for name in ("get_fundamentals", "upsert_fundamental", "insert_estimates", "get_estimate_history",
                 "get_prev_grades", "replace_distributions", "upsert_results"):
        monkeypatch.setattr(batch.repo, name, getattr(mem, name))

    async def fake_universe(redis):
        return {s: (f"Co {s}", "information_technology") for s in SYMS}

    monkeypatch.setattr(batch, "fetch_target_universe", fake_universe)
    monkeypatch.setattr(batch, "FmpClient", lambda client, redis, priority: fake)
    monkeypatch.setattr(batch.settings, "FMP_API_KEY", "k")
    return mem, fake


async def test_batch_end_to_end(env):
    mem, fake = env
    summary = await batch.run_us_batch(AS_OF, redis=None, client=None)  # type: ignore[arg-type]
    assert summary["ok"] and summary["universe"] == 25
    assert summary["computed"] == 24                      # T03 拉价失败，当天不重算
    assert {r["symbol"] for r in mem.results} == set(SYMS) - {"T03"}
    assert len(mem.fund) == 25                            # 无快照 → 全部拉报表
    assert all(r["snapshot_date"] == AS_OF and r["market"] == "us" for r in mem.est)
    assert ("_all", "_overall") in mem.dists and len(mem.dists[("_all", "_overall")]) == 24
    assert len(mem.dists[("information_technology", "pe_ttm")]) == 24

    r = next(x for x in mem.results if x["symbol"] == "T00")
    zh, en = r["payload_zh"], r["payload_en"]
    assert zh["status"] == "ok" and zh["peer_group"]["sample_size"] == 24
    assert zh["dimensions"][4]["status"] == "accumulating"
    assert en["dimensions"][0]["name"] == "Valuation"
    # 股价最低的 T00 估值最便宜：前瞻 PE 百分位应是板块最高
    pe = next(m for g in zh["dimensions"][0]["groups"] for m in g["metrics"] if m["key"] == "pe_fwd")
    assert pe["percentile"] == 100.0
    assert r["grades"]["overall"] == zh["overall"]["grade"]


def test_estimate_rows_keeps_recent_fiscal_years():
    rows = batch.estimate_rows("us", "NVDA", AS_OF, raw("NVDA", "est"))
    dates = sorted(r["fiscal_date"] for r in rows)
    assert dates[0] >= "2025-09-30" and "2027-01-25" in dates
    assert all(r["n_analysts"] >= 0 for r in rows)


def test_needs_refresh():
    from datetime import datetime

    class Snap:
        fetched_at = datetime(2026, 9, 1)
        filing_date = "2026-08-26"

    assert batch.needs_refresh(None, {}, "A", AS_OF)
    assert not batch.needs_refresh(Snap(), {}, "A", AS_OF)
    # 9-25 发布财报，库里最新报表 8-26 披露 → FMP 还没更新新季度，每天重拉
    assert batch.needs_refresh(Snap(), {"A": "2026-09-25"}, "A", AS_OF)
    # 拿到新季度（披露日不早于发布日）后停止
    Snap.filing_date = "2026-09-25"
    assert not batch.needs_refresh(Snap(), {"A": "2026-09-25"}, "A", AS_OF)
    Snap.fetched_at = datetime(2026, 5, 1)
    assert batch.needs_refresh(Snap(), {}, "A", AS_OF)


async def test_missing_key_fails_loudly(monkeypatch):
    monkeypatch.setattr(batch.settings, "FMP_API_KEY", "")
    summary = await batch.run_us_batch(AS_OF, redis=None, client=None)  # type: ignore[arg-type]
    assert summary == {"ok": False, "reason": "missing_fmp_key"}
