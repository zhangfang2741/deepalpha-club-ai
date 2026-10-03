"""A 股 / 港股夜间批量与样本外单只现算。评分、落库与美股共用 batch.score_and_store。

A 股：全市场按报告期批量拉报表（历史报告期不变，平时只刷新仍在披露窗口内的期次；每 30 天全量一次兜底修订），
     只为样本股票（总市值前 1800）存快照；新进样本、没有历史的股票按代码补拉。
港股：逐只拉报表，只在出现新报告期、无快照或快照超过 90 天时重拉。
两地都每天为样本股票拉一致预期（写快照，只补不覆盖）与前复权收盘价。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from redis.asyncio import Redis

from app.core.logging import logger
from app.services.quant_research import repository as repo
from app.services.quant_research.batch import score_and_store
from app.services.quant_research.cnhk import cn_source, eastmoney as em, etnet, hk_source
from app.services.quant_research.cnhk.etnet import CURRENCY_NAMES
from app.services.quant_research.cnhk.http import new_client
from app.services.quant_research.cnhk.pipeline import (
    build_cnhk_inputs,
    cn_estimates,
    cny_per,
    estimate_rows_for,
    fetch_prices,
    hk_estimates,
)
from app.services.quant_research.cnhk.reports import merge_reports
from app.services.quant_research.inputs import StockInputs

CN_FULL_MARKER = "quant:cn:fundamentals_full:v1"
CN_FULL_EVERY = 30 * 86400
HK_REFRESH_AFTER_DAYS = 90
_STOCK_CONCURRENCY = 6     # 每只股票串起 2~5 个请求；各站点速率由 http 闸门控制，这里只限同时在途的股票数
_MIN_REPORTS = 6           # 少于 6 个报告期视为历史不全，按代码补拉
KEEP_REPORTS = 24          # 快照只留最近 24 个报告期（换算 16 季 + 3 年复合只需约 17 期）


@dataclass
class Collected:
    inputs: StockInputs | None
    estimate_rows: list[dict]


# ---------- A 股 ----------

async def collect_cn(client: httpx.AsyncClient, code: str, meta: cn_source.CnMeta, reports: list[dict],
                     balance: dict | None, as_of: date, redis: Redis | None) -> Collected:
    """一只 A 股：一致预期 + 收盘价 → StockInputs（报表由调用方提供）。"""
    f10, prices = await asyncio.gather(em.f10_forecast(client, code), fetch_prices(code, as_of, redis))
    est = cn_estimates(f10)
    rows = estimate_rows_for("cn", code, as_of, est)
    if not prices or not reports or not meta.sector:
        logger.warning("quant_cn_symbol_incomplete", symbol=code, prices=len(prices), reports=len(reports))
        return Collected(None, rows)
    inp = build_cnhk_inputs(market="cn", symbol=code, name=meta.name, sector=meta.sector, as_of=as_of,
                            reports=reports, balance=balance, estimates=est, prices=prices, shares=meta.shares)
    return Collected(inp, rows)


def _newest_balance(*balances: dict | None) -> dict | None:
    known = [b for b in balances if b]
    return max(known, key=lambda b: b.get("date") or "") if known else None


async def _refresh_cn_fundamentals(client: httpx.AsyncClient, universe: list[str], as_of: date,
                                   redis: Redis | None) -> dict[str, tuple[list[dict], dict | None]]:
    """样本股票的累计报告与最新资产负债表（DB 快照 + 本次刷新的报告期），有变化的写回 DB。"""
    snaps = await repo.get_fundamentals("cn", universe)
    full = len(snaps) < 0.8 * len(universe)
    if not full and redis is not None:
        try:
            full = not await redis.exists(CN_FULL_MARKER)
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_cn_marker_read_failed", error=str(e))
    periods = cn_source.quarter_ends(cn_source.FIRST_PERIOD, as_of) if full else cn_source.open_periods(as_of)
    balance_periods = cn_source.quarter_ends(as_of - timedelta(days=200), as_of)[-2:]
    fetched = await cn_source.fetch_periods(client, periods, balance_periods, set(universe)) if periods else {}

    out: dict[str, tuple[list[dict], dict | None]] = {}
    changed: list[dict] = []
    for code in universe:
        snap, new = snaps.get(code), fetched.get(code) or {}
        old_reports = merge_reports(list(snap.income_quarters) if snap else [], [])[:KEEP_REPORTS]  # 规范成新 → 旧
        reports = merge_reports(old_reports, new.get("reports") or [])[:KEEP_REPORTS]
        balance = _newest_balance(snap.balance if snap else None, *(new.get("balances") or []))
        out[code] = (reports, balance)
        if reports != old_reports or (balance != (snap.balance if snap else None)):
            changed.append({"symbol": code, "reports": reports, "balance": balance})

    # 新进样本 / 历史不全：按代码补拉全部报告期
    missing = [c for c in universe if len(out[c][0]) < _MIN_REPORTS]
    sem = asyncio.Semaphore(_STOCK_CONCURRENCY)

    async def backfill(code: str) -> None:
        async with sem:
            try:
                one = await cn_source.fetch_symbol(client, code)
            except Exception as e:  # noqa: BLE001
                logger.warning("quant_cn_backfill_failed", symbol=code, error=str(e))
                return
        if one and one["reports"]:
            reports = merge_reports(out[code][0], one["reports"])[:KEEP_REPORTS]
            balance = _newest_balance(out[code][1], *(one.get("balances") or []))
            out[code] = (reports, balance)
            changed.append({"symbol": code, "reports": reports, "balance": balance})

    if missing and not full:
        await asyncio.gather(*(backfill(c) for c in missing))
    if changed:
        await repo.upsert_raw_reports("cn", list({r["symbol"]: r for r in changed}.values()))
    if full and redis is not None:
        try:
            await redis.set(CN_FULL_MARKER, as_of.isoformat(), ex=CN_FULL_EVERY)
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_cn_marker_write_failed", error=str(e))
    logger.info("quant_cn_fundamentals_refreshed", full=full, periods=len(periods), changed=len(changed),
                backfilled=len(missing) if not full else 0)
    return out


async def run_cn_batch(as_of: date, *, redis: Redis | None, limit: int | None = None) -> dict:
    """A 股样本（总市值前 1800）全量计算并落库，返回摘要。limit 只用于本地试跑。"""
    started = datetime.now(UTC)
    async with new_client() as client:
        meta = await cn_source.fetch_market_meta(client)
        universe = cn_source.pick_universe(meta)[:limit] if limit else cn_source.pick_universe(meta)
        if not universe:
            logger.error("quant_cn_empty_universe")
            return {"ok": False, "market": "cn", "reason": "empty_universe"}
        fundamentals = await _refresh_cn_fundamentals(client, universe, as_of, redis)
        inputs, est_rows = await _collect_all(
            universe, lambda c: collect_cn(client, c, meta[c], *fundamentals[c], as_of, redis))
    return await score_and_store("cn", as_of, inputs, est_rows, redis=redis, universe_size=len(universe),
                                 started=started)


async def _collect_all(universe: list[str], fn) -> tuple[dict[str, StockInputs], list[dict]]:
    sem = asyncio.Semaphore(_STOCK_CONCURRENCY)
    inputs: dict[str, StockInputs] = {}
    est_rows: list[dict] = []

    async def one(code: str) -> None:
        async with sem:
            try:
                got: Collected = await fn(code)
            except Exception as e:  # noqa: BLE001 单只失败不影响整批
                logger.exception("quant_cnhk_symbol_failed", symbol=code, error=str(e))
                return
        est_rows.extend(got.estimate_rows)
        if got.inputs is not None:
            inputs[code] = got.inputs

    await asyncio.gather(*(one(c) for c in universe))
    return inputs, est_rows


# ---------- 港股 ----------

def hk_needs_refresh(snap, m: hk_source.HkMeta, as_of: date) -> bool:
    """无快照、出现了更新的报告期、或快照超过 90 天。"""
    if snap is None or not snap.income_quarters:
        return True
    if m.latest_report and (snap.latest_quarter_date or "") < m.latest_report:
        return True
    fetched = snap.fetched_at.date() if snap.fetched_at else None
    return fetched is None or (as_of - fetched).days > HK_REFRESH_AFTER_DAYS


class FxBook:
    """一轮计算内的汇率（1 单位折合多少人民币），按需取、取过就记住。"""

    def __init__(self, client: httpx.AsyncClient, redis: Redis | None, priority: str):
        """priority：批量用 batch 额度，用户实时请求用 user 额度（见 fmp_budget）。"""
        self._client, self._redis, self._priority = client, redis, priority
        self._rates: dict[str, float] = {"CNY": 1.0}
        self._lock = asyncio.Lock()

    async def rate(self, currency: str) -> float | None:
        async with self._lock:
            if currency not in self._rates:
                self._rates.update(await cny_per({currency}, client=self._client, redis=self._redis,
                                                 priority=self._priority))
            return self._rates.get(currency)


async def collect_hk(client: httpx.AsyncClient, m: hk_source.HkMeta, snap, as_of: date, redis: Redis | None,
                     fx: FxBook, *, store: bool) -> Collected:
    """一只港股：报表（需要时重拉并写回）+ 一致预期 + 收盘价 → StockInputs（金额折成港元）。"""
    if hk_needs_refresh(snap, m, as_of):
        reports, balance = await hk_source.fetch_reports(client, m, as_of)
        if reports and store:
            await repo.upsert_raw_reports("hk", [{"symbol": m.code, "reports": reports, "balance": balance}])
        if not reports and snap is not None:
            reports, balance = list(snap.income_quarters), snap.balance
    else:
        reports, balance = list(snap.income_quarters), snap.balance
    report_cur = CURRENCY_NAMES.get(str((reports[0] if reports else {}).get("currency") or ""))
    html, prices = await asyncio.gather(etnet.fetch(client, m.code), fetch_prices(m.code, as_of, redis))
    fc = etnet.parse(html, report_cur) if html else None
    est = hk_estimates(fc, m.fy_end, as_of)
    rows = estimate_rows_for("hk", m.code, as_of, est)
    hkd = await fx.rate("HKD")
    est_cur = fc.currency if fc else None
    est_rate = await fx.rate(est_cur) if est_cur else None
    if not prices or not reports or not m.sector or hkd is None:
        logger.warning("quant_hk_symbol_incomplete", symbol=m.code, prices=len(prices), reports=len(reports))
        return Collected(None, rows)
    if est and est_rate is None:  # 预期币种换不了汇率：宁可不用预期，也不要混币种
        est = []
    inp = build_cnhk_inputs(market="hk", symbol=m.code, name=m.name, sector=m.sector, as_of=as_of,
                            reports=reports, balance=balance, estimates=est, prices=prices, shares=m.shares,
                            amount_scale=1 / hkd, estimate_scale=(est_rate or 1.0) / hkd,
                            fx={"hkd_cny": hkd, "estimate_currency": est_cur})
    return Collected(inp, rows)


async def run_hk_batch(as_of: date, *, redis: Redis | None, limit: int | None = None) -> dict:
    """港股样本（港股通 ∪ 市值 ≥ 20 亿港元）全量计算并落库，返回摘要。"""
    started = datetime.now(UTC)
    async with new_client() as client, httpx.AsyncClient() as fmp_client:
        meta = await hk_source.fetch_meta(client, as_of)
        universe = hk_source.pick_universe(meta)[:limit] if limit else hk_source.pick_universe(meta)
        if not universe:
            logger.error("quant_hk_empty_universe")
            return {"ok": False, "market": "hk", "reason": "empty_universe"}
        snaps = await repo.get_fundamentals("hk", universe)
        refreshed = sum(1 for c in universe if hk_needs_refresh(snaps.get(c), meta[c], as_of))
        fx = FxBook(fmp_client, redis, "batch")
        inputs, est_rows = await _collect_all(
            universe, lambda c: collect_hk(client, meta[c], snaps.get(c), as_of, redis, fx, store=True))
    return await score_and_store("hk", as_of, inputs, est_rows, redis=redis, universe_size=len(universe),
                                 started=started, extra={"refreshed": refreshed})
