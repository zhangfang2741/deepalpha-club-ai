"""夜间批量：美股标普1500 量化研究全量计算 + A 股一致预期快照。

美股流程（run_us_batch）：
  成分 → 需要时重拉报表（新披露 / 无快照 / 超 100 天）→ 每只拉一致预期（写快照，只补不覆盖）与收盘价
  → 全体指标（含 EPS 修正）→ 板块分布 → 维度分 → 综合分分布 → 综合等级（防抖）→ 中英响应落库。
所有 FMP 调用 priority="batch"（受批量额度与 429 熔断约束，见 app/cache/fmp_budget）。
某只股票拉价失败时当天不重算它，接口继续返回它上一次的结果（as_of 如实是旧日期）。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from datetime import UTC, date, datetime, timedelta

import httpx
from redis.asyncio import Redis

from app.cache.operations import scan_keys
from app.core.config import settings
from app.core.logging import logger
from app.services.quant_research import repository as repo
from app.services.quant_research.builder import (
    revision_metrics,
    Evaluation,
    build_payload,
    evaluate,
    finalize_overall,
    grades_of,
    sector_sample_sizes,
)
from app.services.quant_research.eps_trend import fetch_eps_trend, needs_trend
from app.services.quant_research.fmp import FmpClient
from app.services.quant_research.revisions import EstimatePoint, accumulated_days
from app.services.quant_research.inputs import StockInputs, build_inputs
from app.services.quant_research.metrics import MetricValue, compute_metrics
from app.services.quant_research.scoring import (
    OVERALL_KEY,
    OVERALL_SECTOR,
    build_cohort_distributions,
    build_dim_distributions,
    build_distributions,
)
from app.services.quant_research.universe import fetch_sp1500

MARKET = "us"
EARNINGS_WINDOW_DAYS = 30
KEY_TTL = 3 * 86400
REFRESH_AFTER_DAYS = 100
HISTORY_DAYS = 120
_CONCURRENCY = 12  # 速率由全局 FMP 预算控制（批量 ≤150/分钟），并发只用来掩盖接口延迟


def estimate_rows(market: str, symbol: str, snapshot_date: date, estimates: list[dict]) -> list[dict]:
    """一致预期 → 快照行：只存财年截止日在一年前之后的条目（覆盖 FY0 / FY1 / FY2 …）。"""
    cutoff = (snapshot_date - timedelta(days=365)).isoformat()
    rows = []
    for e in estimates:
        d = str(e.get("date", ""))[:10]
        if not d or d < cutoff:
            continue
        rows.append({
            "market": market, "symbol": symbol, "snapshot_date": snapshot_date, "fiscal_date": d,
            "eps_avg": e.get("epsAvg"), "eps_low": e.get("epsLow"), "eps_high": e.get("epsHigh"),
            "revenue_avg": e.get("revenueAvg"), "ebitda_avg": e.get("ebitdaAvg"), "ebit_avg": e.get("ebitAvg"),
            "n_analysts": int(e.get("numAnalystsEps") or 0),
        })
    return rows


def needs_refresh(snapshot, reported: dict[str, str], symbol: str, as_of: date) -> bool:
    """是否需要重拉报表：无快照、快照超过 100 天，或近期发布了财报而库里还是旧季度。

    FMP 的报表常比财报发布晚几天才更新：只要库里最新报表的披露日早于这次财报发布日，
    每天都重拉，直到拿到新季度（窗口 30 天，见 EARNINGS_WINDOW_DAYS）。
    """
    if snapshot is None:
        return True
    fetched = snapshot.fetched_at.date() if snapshot.fetched_at else None
    if fetched is None or (as_of - fetched).days > REFRESH_AFTER_DAYS:
        return True
    reported_on = reported.get(symbol)
    return reported_on is not None and (snapshot.filing_date or "") < reported_on


async def _recent_reports(fmp: FmpClient, as_of: date) -> dict[str, str]:
    """最近 EARNINGS_WINDOW_DAYS 天内发布过财报的公司 → 最近一次发布日。"""
    cal = await fmp.earnings_calendar(as_of - timedelta(days=EARNINGS_WINDOW_DAYS), as_of) or []
    out: dict[str, str] = {}
    for r in cal:
        if isinstance(r, dict) and r.get("epsActual") is not None and r.get("symbol") and r.get("date"):
            sym, d = str(r["symbol"]), str(r["date"])[:10]
            if d > out.get(sym, ""):
                out[sym] = d
    return out


async def _collect_one(fmp: FmpClient, symbol: str, sector: str, name: str, as_of: date, snapshot,
                       refresh: bool) -> tuple[StockInputs | None, list[dict]]:
    if refresh:
        income, cash, bal = await asyncio.gather(fmp.income_quarters(symbol), fmp.cash_quarters(symbol),
                                                 fmp.balance_latest(symbol))
        if isinstance(income, list) and income:
            income = sorted(income, key=lambda q: q.get("date", ""), reverse=True)
            cash = sorted(cash or [], key=lambda q: q.get("date", ""), reverse=True) if isinstance(cash, list) else []
            balance = bal[0] if isinstance(bal, list) and bal else None
            await repo.upsert_fundamental(MARKET, symbol, income, cash, balance)
        elif snapshot is not None:
            income, cash, balance = snapshot.income_quarters, snapshot.cash_quarters, snapshot.balance
        else:
            logger.warning("quant_batch_no_fundamentals", symbol=symbol)
            return None, []
    else:
        income, cash, balance = snapshot.income_quarters, snapshot.cash_quarters, snapshot.balance
    estimates, prices = await asyncio.gather(fmp.estimates_annual(symbol), fmp.price_light(symbol, as_of))
    if not isinstance(prices, list) or not prices:
        logger.warning("quant_batch_price_failed", symbol=symbol)
        return None, []
    est = estimates if isinstance(estimates, list) else []
    inp = build_inputs(symbol=symbol, as_of=as_of, sector_key=sector, income=income, cash=cash, balance=balance,
                       estimates=est, prices=prices, name=name)
    return inp, estimate_rows(MARKET, symbol, as_of, est)


async def run_us_batch(as_of: date, *, redis: Redis | None, client: httpx.AsyncClient,
                       limit: int | None = None, sectors: set[str] | None = None) -> dict:
    """美股标普1500 全量计算并落库，返回摘要。limit / sectors 只用于本地试跑（取部分板块或前 N 只）。"""
    started = datetime.now(UTC)
    if not settings.FMP_API_KEY:
        logger.error("quant_batch_missing_fmp_key")
        return {"ok": False, "reason": "missing_fmp_key"}
    fmp = FmpClient(client, redis, "batch")
    universe = await fetch_sp1500(redis)
    if sectors:
        universe = {k: v for k, v in universe.items() if v[1] in sectors}
    symbols = sorted(universe)[:limit] if limit else sorted(universe)
    if not symbols:
        logger.error("quant_batch_empty_universe")
        return {"ok": False}

    snapshots = await repo.get_fundamentals(MARKET, symbols)
    reported = await _recent_reports(fmp, as_of)

    sem = asyncio.Semaphore(_CONCURRENCY)
    inputs: dict[str, StockInputs] = {}
    est_rows: list[dict] = []

    async def one(sym: str) -> None:
        name, sector = universe[sym]
        async with sem:
            try:
                snap = snapshots.get(sym)
                inp, rows = await _collect_one(fmp, sym, sector, name, as_of, snap,
                                               needs_refresh(snap, reported, sym, as_of))
            except Exception as e:  # noqa: BLE001 单只失败不影响整批
                logger.exception("quant_batch_symbol_failed", symbol=sym, error=str(e))
                return
        if inp is not None:
            inputs[sym] = inp
            est_rows.extend(rows)

    await asyncio.gather(*(one(s) for s in symbols))
    refreshed = sum(1 for s in symbols if needs_refresh(snapshots.get(s), reported, s, as_of))
    return await score_and_store(MARKET, as_of, inputs, est_rows, redis=redis, universe_size=len(symbols),
                                 started=started, extra={"refreshed": refreshed})


async def score_and_store(market: str, as_of: date, inputs: dict[str, StockInputs], est_rows: list[dict], *,
                          redis: Redis | None, universe_size: int, started: datetime,
                          extra: dict | None = None) -> dict:
    """三个市场共用的后半段。

    写预期快照 → 全体指标（含 EPS 修正）→ 板块分布 → 维度分 → 综合分分布 → 综合等级（防抖）→ 中英响应落库 → 清缓存。
    """
    inserted = await repo.insert_estimates(est_rows)

    histories = await repo.get_estimate_history(market, list(inputs), as_of - timedelta(days=HISTORY_DAYS))
    if market == MARKET:  # 外部 EPS 趋势过渡只有美股
        await attach_eps_trends(inputs, histories, as_of)
    metrics_all: dict[str, tuple[str, dict[str, MetricValue]]] = {}
    for sym, inp in inputs.items():
        m = compute_metrics(inp) | revision_metrics(inp, histories.get(sym, []))
        metrics_all[sym] = (inp.sector_key, m)
    dists = build_distributions(metrics_all)

    prev = await repo.get_prev_grades(market, as_of)
    evals: dict[str, Evaluation] = {s: evaluate(inp, histories.get(s, []), dists, prev.get(s))
                                    for s, inp in inputs.items()}
    dim_scores: dict[str, list[float]] = {}
    for ev in evals.values():
        for d in ev.dims:
            if d.status == "ok" and d.score is not None:
                dim_scores.setdefault(d.key, []).append(d.score)
    dists |= build_dim_distributions(dim_scores)
    by_dim = {k: sorted(v) for k, v in dim_scores.items()}
    for ev in evals.values():
        ev.dim_dists = by_dim
    overall_dist = sorted(ev.composite for ev in evals.values() if ev.composite is not None)
    dists[(OVERALL_SECTOR, OVERALL_KEY)] = overall_dist
    cohorts = build_cohort_distributions([(ev.stage.key if ev.stage else None, ev.composite)
                                          for ev in evals.values() if ev.composite is not None])
    dists |= cohorts
    samples = sector_sample_sizes(dists)

    rows = []
    for sym, ev in evals.items():
        finalize_overall(ev, overall_dist, prev.get(sym), cohorts)
        n = samples.get(ev.inp.sector_key, 0)
        rows.append({
            "market": market, "symbol": sym, "as_of": as_of, "sector_key": ev.inp.sector_key,
            "payload_zh": build_payload(ev, "zh", in_universe=True, sector_sample=n).model_dump(mode="json"),
            "payload_en": build_payload(ev, "en", in_universe=True, sector_sample=n).model_dump(mode="json"),
            "grades": grades_of(ev),
        })
    if evals:  # 一只都没算出来时不要用空分布覆盖当天
        await repo.replace_distributions(market, as_of, dists)
        await repo.upsert_results(rows)

    if redis is not None and evals:
        try:
            await redis.set(latest_key(market), as_of.isoformat(), ex=KEY_TTL)
            stale = await scan_keys(redis, f"quant:{market}:sym:*")  # SCAN，不用 KEYS 扫全库
            if stale:
                await redis.delete(*stale)
        except Exception as e:  # noqa: BLE001 结果已落库，缓存清理失败只会让旧缓存多活到 TTL
            logger.warning("quant_batch_cache_invalidate_failed", market=market, error=str(e))
    summary = {"ok": bool(evals), "market": market, "as_of": as_of.isoformat(), "universe": universe_size,
               "computed": len(evals), "estimates_inserted": inserted, **(extra or {}),
               "seconds": round((datetime.now(UTC) - started).total_seconds())}
    if evals:
        logger.info("quant_batch_done", **summary)
    else:
        logger.error("quant_batch_nothing_computed", **summary)
    return summary


def latest_key(market: str) -> str:
    """最近一次批量日期（Redis）。"""
    return f"quant:{market}:latest_as_of"


async def attach_eps_trends(inputs: dict[str, StockInputs], histories: dict[str, list[EstimatePoint]],
                            as_of: date) -> int:
    """自有快照不满 90 天的股票补上外部 EPS 趋势（EPS 修正过渡期），返回补上的只数。"""
    todo = [s for s in inputs if needs_trend(accumulated_days(histories.get(s, []), as_of))]

    async def one(sym: str) -> None:
        trend = await fetch_eps_trend(sym)
        if trend is not None:
            inputs[sym] = replace(inputs[sym], eps_trend=trend)

    await asyncio.gather(*(one(s) for s in todo))
    got = sum(1 for s in todo if inputs[s].eps_trend is not None)
    logger.info("quant_eps_trend_attached", requested=len(todo), attached=got)
    return got


def dump_summary(summary: dict) -> str:
    """批量摘要转 JSON 文本（命令行输出用）。"""
    return json.dumps(summary, ensure_ascii=False)
