"""A 股 / 港股样本外股票：按当天的行业分布现算（与美股样本外同一套逻辑），结果由 service 缓存 1 天。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.quant_research import QuantResearchOut
from app.services.quant_research import copy as tx
from app.services.quant_research import repository as repo
from app.services.quant_research.batch import HISTORY_DAYS
from app.services.quant_research.builder import build_payload, evaluate, finalize_overall, insufficient, sector_sample_sizes
from app.services.quant_research.cnhk import cn_source, eastmoney as em, hk_source
from app.services.quant_research.cnhk.batch import Collected, FxBook, collect_cn, collect_hk
from app.services.quant_research.cnhk.http import new_client
from app.services.quant_research.copy import Lang
from app.services.quant_research.scoring import OVERALL_KEY, OVERALL_SECTOR


async def _cn_meta(client: httpx.AsyncClient, code: str) -> cn_source.CnMeta | None:
    rows = await em.table(client, "RPT_VALUEANALYSIS_DET",
                          "SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,TOTAL_MARKET_CAP,TOTAL_SHARES,TRADE_DATE",
                          f'(SECURITY_CODE="{code}")', base=em.WEB, sort=("TRADE_DATE", "-1"), max_pages=1,
                          extra={"pageSize": "1"})
    if not rows:
        return None
    r = rows[0]
    return cn_source.CnMeta(code, str(r.get("SECURITY_NAME_ABBR") or code), r.get("BOARD_NAME"),
                            cn_source.cn_sector(r.get("BOARD_NAME")), cn_source._f(r.get("TOTAL_SHARES")),
                            cn_source._f(r.get("TOTAL_MARKET_CAP")), str(r.get("TRADE_DATE") or "")[:10])


async def compute(market: str, symbol: str, lang: Lang, redis: Redis | None) -> tuple[QuantResearchOut, QuantResearchOut | None]:
    """返回 (请求语言的结果, 另一种语言的结果)；数据不足时第二项为 None。"""
    as_of = await repo.latest_distribution_date(market)
    if as_of is None:
        return insufficient(market, symbol, lang, tx._i(
            lang, "行业基准数据尚未生成：首次批量计算正在进行或尚未开始，完成约需 30~60 分钟",
            "Sector baselines are not ready yet: the first full computation takes about 30-60 minutes")), None
    dists = await repo.get_distributions(market, as_of)
    today = datetime.now(UTC).date()
    async with new_client() as client:
        if market == "cn":
            meta = await _cn_meta(client, symbol)
            if meta is None or meta.sector is None:
                logger.info("quant_on_demand_unmapped", market=market, symbol=symbol)
                return insufficient(market, symbol, lang), None
            one = await cn_source.fetch_symbol(client, symbol)
            got: Collected = await collect_cn(client, symbol, meta, (one or {}).get("reports") or [],
                                              ((one or {}).get("balances") or [None])[0], today, redis)
        else:
            metas = await hk_source.fetch_meta(client, today, codes=[symbol])
            m = metas.get(symbol)
            if m is None or m.sector is None:
                logger.info("quant_on_demand_unmapped", market=market, symbol=symbol)
                return insufficient(market, symbol, lang), None
            async with httpx.AsyncClient() as fmp_client:
                got = await collect_hk(client, m, None, today, redis, FxBook(fmp_client, redis, "user"), store=False)
    await repo.insert_estimates(got.estimate_rows)  # 看过的样本外股票也积累预期快照（只补不覆盖）
    if got.inputs is None:
        return insufficient(market, symbol, lang, tx._i(lang, "暂时无法获取该股票的数据，请稍后再试",
                                                       "Could not fetch data for this symbol, please try again later")), None
    history = (await repo.get_estimate_history(market, [symbol], today - timedelta(days=HISTORY_DAYS)))[symbol]
    ev = evaluate(got.inputs, history, dists)
    finalize_overall(ev, dists.get((OVERALL_SECTOR, OVERALL_KEY), []), None, dists)
    n = sector_sample_sizes(dists).get(got.inputs.sector_key, 0)
    other: Lang = "en" if lang == "zh" else "zh"
    logger.info("quant_on_demand_computed", market=market, symbol=symbol, sector=got.inputs.sector_key)
    return (build_payload(ev, lang, in_universe=False, sector_sample=n),
            build_payload(ev, other, in_universe=False, sector_sample=n))
