"""护城河任务：对标普1500 逐只检查最新 10-K，没评估过的就评估并存档。

部署后冷启动跑一遍（已评估的年报直接跳过），之后每天检查一次新年报。与夜间评分批量互相独立：
大模型判断全量要数小时，不能拖住每日评分；结果在读取时附到响应上，评完一只即可见一只。
FMP 调用经全局预算（batch 优先级）；SEC 与大模型各自限流。单只失败只记日志，下一轮再试。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.services.llm.registry import llm_registry
from app.services.llm.service import llm_service
from app.services.quant_research import repository as repo
from app.services.quant_research.fmp import FmpClient
from app.services.quant_research.moat import METHOD_VERSION
from app.services.quant_research.moat.evidence import compute_evidence
from app.services.quant_research.moat.rating import combine
from app.services.quant_research.moat.sources import QuotaExhausted, judge
from app.services.quant_research.moat.tenk import TenK, business_section, latest_10k
from app.services.quant_research.universe import fetch_sp1500

MARKET = "us"
SYMBOL_CONCURRENCY = 3  # 大模型并发受 sources._llm_gate（4 路）约束；再多只是排队占内存


async def _evidence(fmp: FmpClient, symbol: str, financial: bool, total_debt: float | None) -> dict | None:
    km = await fmp.get("key-metrics", symbol=symbol, period="annual", limit=10)
    prof = await fmp.get("profile", symbol=symbol)
    if not isinstance(km, list) or not km:
        return None
    field = "returnOnEquity" if financial else "returnOnInvestedCapital"
    years = [(int(r["fiscalYear"]), float(r[field])) for r in km
             if r.get(field) is not None and str(r.get("fiscalYear", "")).isdigit()]
    p = prof[0] if isinstance(prof, list) and prof else {}
    mcap = p.get("marketCap") or km[0].get("marketCap")
    ev = compute_evidence(years, beta=p.get("beta"), market_cap=mcap, total_debt=total_debt, financial=financial)
    return ev.to_dict()


def _model_name() -> str:
    """当前实际使用的模型名（默认模型不存在时 llm_service 会回退到注册表第一个）。"""
    names = llm_registry.get_all_names()
    idx = getattr(llm_service, "_current_model_index", 0)
    return names[idx] if 0 <= idx < len(names) else settings.DEFAULT_LLM_MODEL


async def assess(client: httpx.AsyncClient, fmp: FmpClient, symbol: str, sector_key: str, tenk: TenK,
                 total_debt: float | None) -> dict | None:
    """评估一只股票的一份年报，返回待存档的行；数据不足返回 None。"""
    evidence = await _evidence(fmp, symbol, sector_key == "financials", total_debt)
    if evidence is None:
        logger.info("quant_moat_no_evidence", symbol=symbol)
        return None
    section = await business_section(client, tenk)
    if section is None:
        return None
    judgement, votes = await judge(section, symbol)
    sources = [dict(s.model_dump(), votes=v) for s, v in zip(judgement.sources, votes, strict=True)]
    rating = combine(evidence["level"], [s["strength"] for s in sources])
    return {
        "market": MARKET, "symbol": symbol, "accession": tenk.accession, "filed_date": tenk.filed_date,
        "tenk_url": tenk.url, "method_version": METHOD_VERSION, "rating": rating, "trend": evidence["trend"],
        "evidence": evidence, "sources": sources,
        "threats": {"zh": judgement.threats_zh, "en": judgement.threats_en},
        "model_name": _model_name(),
        "assessed_at": datetime.now(UTC).replace(tzinfo=None),
    }


async def run_moat_job(redis: Redis | None, *, symbols: list[str] | None = None) -> dict:
    """对样本（或指定股票）检查最新 10-K 并补齐评估，返回摘要。"""
    started = datetime.now(UTC)
    universe = await fetch_sp1500(redis)
    todo = sorted(symbols or universe)
    done = await repo.moat_assessed(MARKET, METHOD_VERSION)
    # 从没评估过的先跑，让冷启动尽快覆盖更多股票
    todo.sort(key=lambda s: (s in done, s))
    fundamentals = await repo.get_fundamentals(MARKET, todo)
    counts = {"checked": 0, "attempted": 0, "assessed": 0, "skipped": 0, "no_10k": 0, "failed": 0, "deferred": 0}
    sem = asyncio.Semaphore(SYMBOL_CONCURRENCY)
    # 大模型套餐与 App 对话 / 翻译共用：每轮最多新评估 daily_limit 只；用量到顶立即收工，剩下的明天再评
    daily_limit = settings.QUANT_MOAT_DAILY_LIMIT
    stop = {"quota": False}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        fmp = FmpClient(client, redis, "batch")

        async def one(sym: str) -> None:
            async with sem:
                if stop["quota"] or counts["attempted"] >= daily_limit:
                    counts["deferred"] += 1
                    return
                try:
                    tenk = await latest_10k(client, sym)
                    counts["checked"] += 1
                    if tenk is None:
                        counts["no_10k"] += 1
                        return
                    if tenk.accession in done.get(sym, set()):
                        counts["skipped"] += 1
                        return
                    snap = fundamentals.get(sym)
                    debt = (snap.balance or {}).get("totalDebt") if snap else None
                    sector = universe.get(sym, ("", ""))[1]
                    if counts["attempted"] >= daily_limit:
                        counts["deferred"] += 1
                        return
                    counts["attempted"] += 1
                    row = await assess(client, fmp, sym, sector, tenk, debt)
                    if row is not None and await repo.insert_moat(row):
                        counts["assessed"] += 1
                        logger.info("quant_moat_assessed", symbol=sym, rating=row["rating"], trend=row["trend"],
                                    progress=counts["checked"], total=len(todo))
                except QuotaExhausted as e:
                    stop["quota"] = True
                    counts["deferred"] += 1
                    logger.warning("quant_moat_quota_exhausted_stop", symbol=sym, error=str(e))
                except Exception as e:  # noqa: BLE001 单只失败不影响整批
                    counts["failed"] += 1
                    logger.exception("quant_moat_symbol_failed", symbol=sym, error=str(e))

        await asyncio.gather(*(one(s) for s in todo))

    summary = {**counts, "universe": len(todo), "seconds": round((datetime.now(UTC) - started).total_seconds())}
    logger.info("quant_moat_job_done", **summary)
    return summary
