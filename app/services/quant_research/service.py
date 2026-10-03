"""请求入口：读当日批量结果；样本外美股按当日板块分布现算；Redis 缓存。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from dataclasses import replace

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.quant_research import MoatOut, QuantResearchOut
from app.services.quant_research import repository as repo
from app.services.quant_research.cnhk import on_demand as cnhk_on_demand
from app.services.quant_research.batch import HISTORY_DAYS, MARKET, estimate_rows
from app.services.quant_research.builder import (
    METHODOLOGY_VERSION,
    build_payload,
    evaluate,
    finalize_overall,
    insufficient,
    sector_sample_sizes,
    unsupported,
)
from app.services.quant_research import copy as tx
from app.services.quant_research.copy import Lang
from app.services.quant_research.education import enrich_education
from app.services.quant_research.fmp import FmpClient
from app.services.quant_research.eps_trend import fetch_eps_trend, needs_trend
from app.services.quant_research.inputs import build_inputs
from app.services.quant_research.moat import METHOD_VERSION as MOAT_METHOD_VERSION
from app.services.quant_research.markets import normalize_symbol, profile
from app.services.quant_research.moat.present import moat_out, moat_placeholder
from app.services.quant_research.revisions import accumulated_days
from app.services.quant_research.scoring import OVERALL_KEY, OVERALL_SECTOR
from app.services.quant_research.universe import FMP_SECTOR_TO_GICS

RESULT_TTL = 6 * 3600          # 批量跑完会主动清缓存
ON_DEMAND_TTL = 86400


SUPPORTED_MARKETS = ("us", "cn", "hk")


def _cache_key(symbol: str, lang: str, market: str = MARKET) -> str:
    """带方法版本：改规则部署后旧口径缓存立即失效（样本外现算结果缓存 24 小时，否则要等批量跑完才清）。"""
    return f"quant:{market}:sym:{METHODOLOGY_VERSION}:{symbol}:{lang}"


async def get_quant_research(market: str, symbol: str, lang: Lang, *, redis: Redis | None) -> QuantResearchOut:
    """评分结果（缓存 → 当日批量 → 样本外现算）+ 护城河（仅美股；读取时附上，评完一只即可见一只）。"""
    out = await _get_scores(market, symbol, lang, redis=redis)
    if out.status == "ok" and profile(out.market).has_moat:
        out.moat = await _moat(out.symbol, lang, in_universe=bool(out.peer_group and out.peer_group.in_universe))
    return out


async def _moat(symbol: str, lang: Lang, *, in_universe: bool) -> MoatOut:
    try:
        row = await repo.latest_moat(MARKET, symbol, MOAT_METHOD_VERSION)
    except Exception as e:  # noqa: BLE001 护城河读取失败不影响评分结果
        logger.warning("quant_moat_read_failed", symbol=symbol, error=str(e))
        row = None
    return moat_out(row, lang) if row is not None else moat_placeholder(lang, in_universe=in_universe)


async def _get_scores(market: str, symbol: str, lang: Lang, *, redis: Redis | None) -> QuantResearchOut:
    """缓存 → 当日批量结果 → 样本外现算。"""
    market = market.lower()
    if market not in SUPPORTED_MARKETS:
        return unsupported(market, symbol.upper(), lang)
    symbol = normalize_symbol(market, symbol)

    key = _cache_key(symbol, lang, market)
    if redis is not None:
        try:
            cached = await get_json(redis, key)
            if cached:
                return enrich_education(QuantResearchOut(**cached), lang)
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_cache_read_failed", symbol=symbol, error=str(e))

    row = await repo.get_latest_result(market, symbol)
    if row is not None:
        out = enrich_education(QuantResearchOut(**(row.payload_zh if lang == "zh" else row.payload_en)), lang)
        await _cache(redis, key, out, RESULT_TTL)
        return out

    if market == MARKET:
        out = await _compute_on_demand(symbol, lang, redis)
    else:
        out, other = await cnhk_on_demand.compute(market, symbol, lang, redis)
        if other is not None:
            await _cache(redis, _cache_key(symbol, "en" if lang == "zh" else "zh", market), other, ON_DEMAND_TTL)
    if out.status == "ok":
        await _cache(redis, key, out, ON_DEMAND_TTL)
    return out


async def _cache(redis: Redis | None, key: str, out: QuantResearchOut, ttl: int) -> None:
    if redis is None:
        return
    try:
        await set_json(redis, key, out.model_dump(mode="json"), expire=ttl)
    except Exception as e:  # noqa: BLE001
        logger.warning("quant_cache_write_failed", key=key, error=str(e))


async def _compute_on_demand(symbol: str, lang: Lang, redis: Redis | None) -> QuantResearchOut:
    as_of = await repo.latest_distribution_date(MARKET)
    if as_of is None:
        return insufficient(
            MARKET, symbol, lang,
            tx._i(lang, "板块基准数据尚未生成：首次批量计算正在进行或尚未开始，完成约需 30~60 分钟",
                  "Sector baselines are not ready yet: the first full computation takes about 30-60 minutes"))
    dists = await repo.get_distributions(MARKET, as_of)
    async with httpx.AsyncClient() as client:
        fmp = FmpClient(client, redis, "user")
        profile = await fmp.profile(symbol)
        prof = profile[0] if isinstance(profile, list) and profile else None
        sector = FMP_SECTOR_TO_GICS.get(str(prof.get("sector"))) if prof else None
        if sector is None:
            logger.info("quant_on_demand_unmapped", symbol=symbol, sector=prof.get("sector") if prof else None)
            return insufficient(MARKET, symbol, lang)
        income, cash, bal, est, px = (
            await fmp.income_quarters(symbol), await fmp.cash_quarters(symbol), await fmp.balance_latest(symbol),
            await fmp.estimates_annual(symbol), await fmp.price_light(symbol, date.today()),
        )
    if not isinstance(income, list) or not income or not isinstance(px, list) or not px:
        return insufficient(MARKET, symbol, lang,
                            tx._i(lang, "暂时无法获取该股票的数据，请稍后再试",
                                  "Could not fetch data for this symbol, please try again later"))
    today = datetime.now(UTC).date()
    est_list = est if isinstance(est, list) else []
    # 看过的样本外股票也存一份当日预期，EPS 修正历史随之积累（只补不覆盖）
    await repo.insert_estimates(estimate_rows(MARKET, symbol, today, est_list))
    history = (await repo.get_estimate_history(MARKET, [symbol], today - timedelta(days=HISTORY_DAYS)))[symbol]
    inp = build_inputs(symbol=symbol, as_of=today, sector_key=sector, income=income,
                       cash=cash if isinstance(cash, list) else None, balance=bal,
                       estimates=est_list, prices=px, name=prof.get("companyName") if prof else None)
    if needs_trend(accumulated_days(history, today)):
        inp = replace(inp, eps_trend=await fetch_eps_trend(symbol))
    ev = evaluate(inp, history, dists)
    finalize_overall(ev, dists.get((OVERALL_SECTOR, OVERALL_KEY), []))
    n = sector_sample_sizes(dists).get(sector, 0)
    out = build_payload(ev, lang, in_universe=False, sector_sample=n)
    other = build_payload(ev, "en" if lang == "zh" else "zh", in_universe=False, sector_sample=n)
    await _cache(redis, _cache_key(symbol, "en" if lang == "zh" else "zh"), other, ON_DEMAND_TTL)
    logger.info("quant_on_demand_computed", symbol=symbol, sector=sector)
    return out
