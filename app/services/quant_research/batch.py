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
from app.services.quant_research.scoring import OVERALL_KEY, OVERALL_SECTOR, build_distributions
from app.services.quant_research.universe import fetch_sp1500

MARKET = "us"
LATEST_KEY = "quant:us:latest_as_of"
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
    inserted = await repo.insert_estimates(est_rows)

    histories = await repo.get_estimate_history(MARKET, list(inputs), as_of - timedelta(days=HISTORY_DAYS))
    await attach_eps_trends(inputs, histories, as_of)
    metrics_all: dict[str, tuple[str, dict[str, MetricValue]]] = {}
    for sym, inp in inputs.items():
        m = compute_metrics(inp) | revision_metrics(inp, histories.get(sym, []))
        metrics_all[sym] = (inp.sector_key, m)
    dists = build_distributions(metrics_all)

    prev = await repo.get_prev_grades(MARKET, as_of)
    evals: dict[str, Evaluation] = {s: evaluate(inp, histories.get(s, []), dists, prev.get(s))
                                    for s, inp in inputs.items()}
    overall_dist = sorted(ev.composite for ev in evals.values() if ev.composite is not None)
    dists[(OVERALL_SECTOR, OVERALL_KEY)] = overall_dist
    samples = sector_sample_sizes(dists)

    rows = []
    for sym, ev in evals.items():
        finalize_overall(ev, overall_dist, prev.get(sym))
        n = samples.get(ev.inp.sector_key, 0)
        rows.append({
            "market": MARKET, "symbol": sym, "as_of": as_of, "sector_key": ev.inp.sector_key,
            "payload_zh": build_payload(ev, "zh", in_universe=True, sector_sample=n).model_dump(mode="json"),
            "payload_en": build_payload(ev, "en", in_universe=True, sector_sample=n).model_dump(mode="json"),
            "grades": grades_of(ev),
        })
    await repo.replace_distributions(MARKET, as_of, dists)
    await repo.upsert_results(rows)

    if redis is not None:
        try:
            await redis.set(LATEST_KEY, as_of.isoformat(), ex=KEY_TTL)
            stale = await scan_keys(redis, "quant:us:sym:*")  # SCAN，不用 KEYS 扫全库
            if stale:
                await redis.delete(*stale)
        except Exception as e:  # noqa: BLE001 结果已落库，缓存清理失败只会让旧缓存多活到 TTL
            logger.warning("quant_batch_cache_invalidate_failed", error=str(e))
    summary = {"ok": bool(evals), "as_of": as_of.isoformat(), "universe": len(symbols), "computed": len(evals),
               "estimates_inserted": inserted, "refreshed": sum(1 for s in symbols if needs_refresh(
                   snapshots.get(s), reported, s, as_of)),
               "seconds": round((datetime.now(UTC) - started).total_seconds())}
    if evals:
        logger.info("quant_batch_us_done", **summary)
    else:
        logger.error("quant_batch_us_nothing_computed", **summary)
    return summary


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


# ---------- A 股一致预期快照（为二期 EPS 修正积累历史） ----------

CN_INDEXES = ("000300", "000905")  # 沪深300 + 中证500


def _cn_forecast_blocking(symbol: str) -> list[dict]:
    import akshare as ak

    df = ak.stock_profit_forecast_ths(symbol=symbol, indicator="预测年报每股收益")
    out = []
    for _, r in df.iterrows():
        year = str(r.get("年度") or "").strip()[:4]
        if not year.isdigit():
            continue
        out.append({"fiscal_date": f"{year}-12-31", "eps_avg": _f(r.get("均值")), "eps_low": _f(r.get("最小值")),
                    "eps_high": _f(r.get("最大值")), "n_analysts": int(_f(r.get("预测机构数")) or 0)})
    return out


def _f(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


async def run_cn_estimate_snapshot(as_of: date) -> dict:
    """沪深300 + 中证500 一致预期快照落库（只补不覆盖）。"""
    from app.services.signal_radar.constituents import _fetch_akshare_index

    symbols: list[str] = []
    for idx in CN_INDEXES:
        for sym, _, _ in await _fetch_akshare_index(idx):
            if sym not in symbols:
                symbols.append(sym)
    rows: list[dict] = []
    failed = 0
    for sym in symbols:
        try:
            for r in await asyncio.to_thread(_cn_forecast_blocking, sym):
                rows.append(dict(r, market="cn", symbol=sym, snapshot_date=as_of, revenue_avg=None,
                                 ebitda_avg=None, ebit_avg=None))
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning("quant_cn_forecast_failed", symbol=sym, error=str(e))
        await asyncio.sleep(0.5)  # 数据源礼貌间隔
    inserted = await repo.insert_estimates(rows)
    summary = {"symbols": len(symbols), "rows": len(rows), "inserted": inserted, "failed": failed}
    logger.info("quant_cn_snapshot_done", **summary)
    return summary


def dump_summary(summary: dict) -> str:
    """批量摘要转 JSON 文本（命令行输出用）。"""
    return json.dumps(summary, ensure_ascii=False)
