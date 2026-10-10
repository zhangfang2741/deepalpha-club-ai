"""非 GAAP 实际 EPS 抽样核查（一次性诊断）：对抽样股票各取 1 次财报日历 + 1 次利润表，算两口径近 4 个季度 EPS 之和。

调用经 FmpClient（全局预算、批量优先级），代码不进响应。临时工具，方法稳定后与诊断接口一起删除。
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
from redis.asyncio import Redis

from app.services.quant_research.diagnostics import NgRow
from app.services.quant_research.fmp import FmpClient


def _eps_sum(rows: list, key: str, as_of: date, take: int = 4, skip: int = 0) -> tuple[float | None, int]:
    """已披露季度（日期 ≤ as_of、该字段有值）按日期新 → 旧，跳过 skip 个后取 take 个求和；不足 take 个返回 None。返回 (和, 可用季度总数)。"""
    vals = sorted(((r["date"], float(r[key])) for r in rows if isinstance(r, dict) and r.get("date") and r["date"] <= as_of.isoformat()
                   and isinstance(r.get(key), (int, float))), reverse=True)
    part = vals[skip:skip + take]
    return (round(sum(v for _, v in part), 4) if len(part) == take else None), len(vals)


async def probe(sample: list[tuple[str, str | None, str | None]], as_of: date, redis: Redis | None) -> list[NgRow]:
    """对抽样的每只股票取两口径近 4 个季度 EPS 之和（并发 4，经全局预算）。"""
    async with httpx.AsyncClient() as client:
        fmp = FmpClient(client, redis, "batch")
        sem = asyncio.Semaphore(4)

        async def one(item: tuple[str, str | None, str | None]) -> NgRow:
            sym, sector, stage = item
            async with sem:
                cal = await fmp.get("earnings", symbol=sym, limit=12)
                inc = await fmp.income_quarters(sym, limit=8)
            ng, n_q = _eps_sum(cal if isinstance(cal, list) else [], "epsActual", as_of)
            gaap, _ = _eps_sum(inc if isinstance(inc, list) else [], "epsDiluted", as_of)
            return NgRow(sector, stage, gaap, ng, n_q)

        return list(await asyncio.gather(*(one(i) for i in sample)))
