"""护城河任务：每日上限、用量到顶立即收工（大模型套餐与 App 其它功能共用）。"""

from app.services.quant_research.moat import job
from app.services.quant_research.moat.sources import QuotaExhausted
from app.services.quant_research.moat.tenk import TenK


def _patch(monkeypatch, symbols, assess):
    async def universe(redis):
        return {s: (s, "industrials") for s in symbols}

    async def nothing_done(market, version):
        return {}

    async def no_fundamentals(market, syms):
        return {}

    async def tenk(client, sym):
        return TenK(f"acc-{sym}", "2026-02-01", "u")

    async def insert(row):
        return True

    monkeypatch.setattr(job, "fetch_sp1500", universe)
    monkeypatch.setattr(job.repo, "moat_assessed", nothing_done)
    monkeypatch.setattr(job.repo, "get_fundamentals", no_fundamentals)
    monkeypatch.setattr(job.repo, "insert_moat", insert)
    monkeypatch.setattr(job, "latest_10k", tenk)
    monkeypatch.setattr(job, "assess", assess)


async def test_daily_limit_defers_the_rest(monkeypatch):
    async def assess(*a, **k):
        return {"rating": "none", "trend": None}

    _patch(monkeypatch, [f"S{i}" for i in range(10)], assess)
    monkeypatch.setattr(job.settings, "QUANT_MOAT_DAILY_LIMIT", 4)
    out = await job.run_moat_job(None)
    assert out["assessed"] == 4 and out["deferred"] == 6


async def test_quota_exhausted_stops_the_run(monkeypatch):
    calls = []

    async def assess(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise QuotaExhausted("已达到 Token Plan 用量上限 (2056)")
        return {"rating": "none", "trend": None}

    _patch(monkeypatch, [f"S{i}" for i in range(10)], assess)
    monkeypatch.setattr(job.settings, "QUANT_MOAT_DAILY_LIMIT", 100)
    monkeypatch.setattr(job, "SYMBOL_CONCURRENCY", 1)
    out = await job.run_moat_job(None)
    assert len(calls) == 2 and out["assessed"] == 1 and out["failed"] == 0
    assert out["deferred"] == 9  # 到顶的那只 + 后面 8 只都留到下一轮


async def test_daily_limit_survives_restarts_via_redis(monkeypatch):
    """每日名额记在 Redis：今天已用完（比如之前那次部署跑过），重启后的冷启动不再新评估。"""
    class FakeRedis:
        def __init__(self):
            self.v = {}

        async def incr(self, k):
            self.v[k] = self.v.get(k, 0) + 1
            return self.v[k]

        async def expire(self, k, ttl):
            return True

    async def assess(*a, **k):
        return {"rating": "none", "trend": None}

    async def universe(redis):
        return {s: (s, "industrials") for s in [f"S{i}" for i in range(5)]}

    _patch(monkeypatch, [f"S{i}" for i in range(5)], assess)
    monkeypatch.setattr(job, "fetch_sp1500", universe)
    monkeypatch.setattr(job.settings, "QUANT_MOAT_DAILY_LIMIT", 3)
    r = FakeRedis()
    first = await job.run_moat_job(r)
    second = await job.run_moat_job(r)  # 模拟部署重启后的又一轮
    assert first["assessed"] == 3 and second["assessed"] == 0 and second["deferred"] == 5
