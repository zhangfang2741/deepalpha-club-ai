"""非 GAAP 反事实的后台任务（一次性诊断）：对全体美股取实际 EPS 与现价，算等级变化汇总，结果放进程内存。

全体约 1500 只，每只 1 次财报日历调用 + 每 100 只 1 次批量行情，经 FmpClient（全局预算、批量优先级）；
接口只触发 / 查询进度，不在请求里等。进程重启后结果丢失，需要再触发。临时工具，随诊断接口一起删除。
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
from redis.asyncio import Redis

from app.core.logging import logger
from app.services.quant_research import repository as repo
from app.services.quant_research.diagnostics import NgFull, nongaap_whatif
from app.services.quant_research.fmp import FmpClient
from app.services.quant_research.nongaap_probe import _eps_sum

_STATE: dict = {"state": "idle"}


def state() -> dict:
    """当前任务状态（含进度 / 结果）的副本。"""
    return dict(_STATE)


async def _run(market: str, as_of: date, redis: Redis | None) -> None:
    try:
        rows = await repo.nongaap_whatif_rows(market, as_of)
        _STATE.update(state="running", total=len(rows), done=0)
        async with httpx.AsyncClient() as client:
            fmp = FmpClient(client, redis, "batch")
            prices: dict[str, float] = {}
            syms = [r["symbol"] for r in rows]
            for i in range(0, len(syms), 100):
                q = await fmp.get("batch-quote-short", symbols=",".join(syms[i:i + 100]))
                for x in q if isinstance(q, list) else []:
                    if isinstance(x, dict) and isinstance(x.get("price"), (int, float)) and x.get("symbol"):
                        prices[x["symbol"]] = float(x["price"])
            sem = asyncio.Semaphore(4)

            async def one(r: dict) -> NgFull:
                async with sem:
                    cal = await fmp.get("earnings", symbol=r["symbol"], limit=12)
                    _STATE["done"] = _STATE.get("done", 0) + 1
                cal = cal if isinstance(cal, list) else []
                cur, _ = _eps_sum(cal, "epsActual", as_of)
                prior, _ = _eps_sum(cal, "epsActual", as_of, skip=4)
                return NgFull(r["sector"], r["stage"], r["score"], r["dims"], r["pe_ok"], prices.get(r["symbol"]), cur, prior)

            full = list(await asyncio.gather(*(one(r) for r in rows)))
        _STATE.update(state="done", as_of=as_of.isoformat(), market=market, result=nongaap_whatif(full),
                      price_coverage=round(len(prices) / max(1, len(syms)), 3))
    except Exception as e:  # noqa: BLE001 一次性诊断：失败原因进状态与日志，不抛出
        logger.exception("nongaap_whatif_failed")
        _STATE.update(state="failed", error=str(e)[:200])


async def start(market: str, as_of: date, redis: Redis | None) -> dict:
    """没有在跑就起一个后台任务；已有任务（运行中 / 已完成）则只返回当前状态。"""
    if _STATE.get("state") in ("running", "starting", "done"):
        return state()
    _STATE.clear()
    _STATE.update(state="starting")
    asyncio.get_running_loop().create_task(_run(market, as_of, redis))
    return state()


def reset() -> None:
    """丢弃上次结果，回到空闲。"""
    _STATE.clear()
    _STATE.update(state="idle")
