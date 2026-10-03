"""A 股 / 港股批量编排：报表全量 / 增量判定、合并写回、补拉、港股重拉条件。数据源与 DB 全部替换为假的。"""

from datetime import date, datetime
from types import SimpleNamespace

from app.services.quant_research.cnhk import batch as cb
from app.services.quant_research.cnhk.hk_source import HkMeta


def _rep(d, rev=1.0):
    return {"report_date": d, "notice_date": d, "fy_end": "12-31", "revenue": rev}


class _Redis:
    def __init__(self, marker=False):
        self.store = {cb.CN_FULL_MARKER: "x"} if marker else {}

    async def exists(self, key):
        return key in self.store

    async def set(self, key, value, ex=None):
        self.store[key] = value


async def test_cn_incremental_merges_and_backfills(monkeypatch):
    universe = ["600519", "000001", "000002", "000003", "688999"]  # 4/5 有快照（覆盖率 ≥ 80% 才走增量）
    old = [_rep(f"20{y}-{m}") for y in (24, 25) for m in ("03-31", "06-30", "09-30", "12-31")]
    snaps = {"600519": SimpleNamespace(income_quarters=old, balance={"date": "2025-12-31"}),
             **{c: SimpleNamespace(income_quarters=old, balance={"date": "2025-12-31"})
                for c in ("000001", "000002", "000003")}}
    calls = {"periods": None, "upserted": None, "backfill": []}

    async def get_fundamentals(market, symbols):
        return snaps

    async def fetch_periods(client, periods, balance_periods, keep):
        calls["periods"] = periods
        assert keep == set(universe)
        return {"600519": {"reports": [_rep("2026-06-30", 9.0)], "balances": [{"date": "2026-06-30"}]}}

    async def fetch_symbol(client, code):
        calls["backfill"].append(code)
        return {"reports": [_rep("2026-06-30"), *old], "balances": [{"date": "2026-06-30"}]}

    async def upsert(market, rows):
        calls["upserted"] = sorted(r["symbol"] for r in rows)
        return len(rows)

    monkeypatch.setattr(cb.repo, "get_fundamentals", get_fundamentals)
    monkeypatch.setattr(cb.repo, "upsert_raw_reports", upsert)
    monkeypatch.setattr(cb.cn_source, "fetch_periods", fetch_periods)
    monkeypatch.setattr(cb.cn_source, "fetch_symbol", fetch_symbol)
    out = await cb._refresh_cn_fundamentals(None, universe, date(2026, 10, 3), _Redis(marker=True))  # type: ignore[arg-type]
    assert calls["periods"] == [date(2026, 6, 30), date(2026, 9, 30)]       # 只刷新仍在披露窗口内的期次
    assert out["600519"][0][0]["revenue"] == 9.0 and out["600519"][1] == {"date": "2026-06-30"}
    assert calls["backfill"] == ["688999"]                                   # 新进样本、没有历史 → 按代码补拉
    assert calls["upserted"] == ["600519", "688999"]                         # 其余没变化不写库


async def test_cn_full_when_marker_missing(monkeypatch):
    seen = {}

    async def get_fundamentals(market, symbols):
        return {s: SimpleNamespace(income_quarters=[_rep("2026-06-30")] * 6, balance=None) for s in symbols}

    async def fetch_periods(client, periods, balance_periods, keep):
        seen["n"] = len(periods)
        return {}

    async def upsert(market, rows):
        return 0

    monkeypatch.setattr(cb.repo, "get_fundamentals", get_fundamentals)
    monkeypatch.setattr(cb.repo, "upsert_raw_reports", upsert)
    monkeypatch.setattr(cb.cn_source, "fetch_periods", fetch_periods)
    r = _Redis(marker=False)
    await cb._refresh_cn_fundamentals(None, ["600519"], date(2026, 10, 3), r)  # type: ignore[arg-type]
    assert seen["n"] == 18 and cb.CN_FULL_MARKER in r.store                 # 2022-06-30 起全部 18 期


def test_hk_needs_refresh():
    m = HkMeta("00700", "腾讯", "软件服务", "communication_services", "12-31", "一般企业", 9e9, 3e12, "2026-06-30", True)
    fresh = SimpleNamespace(income_quarters=[_rep("2026-06-30")], latest_quarter_date="2026-06-30",
                            fetched_at=datetime(2026, 9, 1))
    assert cb.hk_needs_refresh(None, m, date(2026, 10, 3))
    assert not cb.hk_needs_refresh(fresh, m, date(2026, 10, 3))
    stale = SimpleNamespace(**{**fresh.__dict__, "latest_quarter_date": "2025-12-31"})
    assert cb.hk_needs_refresh(stale, m, date(2026, 10, 3))                  # 有新报告期
    old = SimpleNamespace(**{**fresh.__dict__, "fetched_at": datetime(2026, 5, 1)})
    assert cb.hk_needs_refresh(old, m, date(2026, 10, 3))                    # 超过 90 天
