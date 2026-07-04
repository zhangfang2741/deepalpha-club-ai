"""机构建仓榜：两段式扫描。

- 第一段（筛选）：全 universe 用 4 个 FMP 快接口排名（跳过期权）。
- 第二段（增强）：对排名靠前的 K 支**补抓期权**，重算仓位维度与状态，
  使 🔥机构建仓 / 💰聪明钱 能在最强的票上真正上榜（否则永远缺失）。
排名用与详情页一致的综合分（缺失维度按中性计入）。
"""
import asyncio
import datetime

import httpx

from app.core.logging import logger
from app.schemas.institutional_signals import (
    LeaderboardEntry,
    LeaderboardResponse,
)
from app.services.institutional_signals.calculator import (
    _composite_score,
    _confidence,
    _coverage,
)
from app.services.institutional_signals.constants import (
    ENRICH_CONCURRENCY,
    ENRICH_TOP_K,
    NASDAQ100_FALLBACK,
    SCAN_CONCURRENCY,
    SCAN_TOP_N,
    SP500_FALLBACK,
)
from app.services.institutional_signals.dimensions import (
    compute_confirmation,
    compute_expectation,
    compute_fundamental,
    compute_participation,
    compute_positioning,
    unavailable_dimension,
)
from app.services.institutional_signals.fetchers import (
    fetch_earnings,
    fetch_grades_historical,
    fetch_insider_statistics,
    fetch_nasdaq100_symbols,
    fetch_option_metrics,
    fetch_price_history,
    fetch_price_target_summary,
    fetch_profile,
    fetch_sp500_symbols,
)
from app.services.institutional_signals.states import derive_states

_PRICE_LOOKBACK_DAYS = 60
# 只把这些「偏多/机会型」状态视为上榜理由（撤退等看空状态不进建仓榜）
_BULLISH_STATES = {
    "institution_accumulation", "expectation_upgrade",
    "breakout_confirmation", "fundamental_turn", "smart_money",
}


def _build_entry(symbol: str, name: str, dims: dict) -> LeaderboardEntry:
    """由维度字典构造榜单行（综合分/状态/top_state）。"""
    states = [s for s in derive_states(dims) if s.key != "neutral"]
    bullish = [s for s in states if s.key in _BULLISH_STATES]
    top_state = max(bullish, key=lambda s: (s.stars, -(s.buy_rank or 9))) if bullish else None
    return LeaderboardEntry(
        symbol=symbol,
        name=name,
        composite_score=_composite_score(dims),
        coverage=_coverage(dims),
        confidence=_confidence(_coverage(dims)),
        top_state=top_state,
        states=states,
        dimension_scores={k: d.score for k, d in dims.items() if d.status != "unavailable"},
    )


async def _score_symbol(
    client: httpx.AsyncClient, symbol: str, sem: asyncio.Semaphore,
    from_date: str, to_date: str,
) -> tuple[LeaderboardEntry, dict, float] | None:
    """第一段评分（4 个 FMP 维度，仓位 unavailable）；返回 (entry, dims, spot)。"""
    async with sem:
        try:
            profile, pt_summary, grades, prices, earnings, insider = await asyncio.gather(
                fetch_profile(client, symbol),
                fetch_price_target_summary(client, symbol),
                fetch_grades_historical(client, symbol),
                fetch_price_history(client, symbol, from_date, to_date),
                fetch_earnings(client, symbol),
                fetch_insider_statistics(client, symbol),
            )
        except Exception as e:
            logger.warning("scan_symbol_failed", symbol=symbol, error=str(e))
            return None

    dims = {
        "expectation": compute_expectation(pt_summary, grades),
        "positioning": unavailable_dimension("positioning", "榜单初筛不含期权，补抓中/点进详情查看"),
        "participation": compute_participation(prices),
        "fundamental": compute_fundamental(earnings),
        "confirmation": compute_confirmation(insider),
    }
    if _coverage(dims) == 0:
        return None  # 全无数据，不入榜

    name = (profile or {}).get("companyName") or (profile or {}).get("name") or symbol
    spot = prices[-1]["close"] if prices else 0.0
    return _build_entry(symbol, name, dims), dims, spot


async def _enrich_symbol(
    entry: LeaderboardEntry, dims: dict, spot: float, sem: asyncio.Semaphore,
) -> LeaderboardEntry:
    """第二段：补抓期权，重算仓位维度与状态（无快照，用水平口径 IV）。"""
    if not spot:
        return entry
    async with sem:
        metrics = await asyncio.to_thread(fetch_option_metrics, entry.symbol, spot)
    if not metrics:
        return entry
    dims = {**dims, "positioning": compute_positioning(metrics)}
    return _build_entry(entry.symbol, entry.name, dims)


def _rank(entries: list[LeaderboardEntry]) -> list[LeaderboardEntry]:
    """有偏多状态的优先，其次综合分——纯函数，便于单测。"""
    return sorted(
        entries,
        key=lambda e: (e.top_state is not None, e.composite_score),
        reverse=True,
    )


async def scan_leaderboard(limit: int = SCAN_TOP_N, universe: str = "sp500") -> LeaderboardResponse:
    """扫描指定 universe 并返回机构建仓榜前 N（在后台任务里调用，不阻塞请求）。

    universe：sp500（标普 500）| nasdaq100（纳指 100 / QQQ）。
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    from_date = (today - datetime.timedelta(days=_PRICE_LOOKBACK_DAYS)).isoformat()
    to_date = today.isoformat()
    sem = asyncio.Semaphore(SCAN_CONCURRENCY)

    async with httpx.AsyncClient(timeout=15) as client:
        if universe == "nasdaq100":
            symbols = await fetch_nasdaq100_symbols(client)
            fallback, source = NASDAQ100_FALLBACK, "nasdaq100"
        else:
            symbols = await fetch_sp500_symbols(client)
            fallback, source = SP500_FALLBACK, "sp500"
        if not symbols:
            # 动态成分股拉取失败 → 用该 universe 专属兜底名单（两个 universe 不同）
            symbols = list(fallback)
            source = f"{source}-fallback"
            logger.warning("scan_universe_fallback", universe=universe, count=len(symbols))

        # 第一段：全 universe 4 维评分
        results = await asyncio.gather(
            *[_score_symbol(client, s, sem, from_date, to_date) for s in symbols]
        )
        scored = [r for r in results if r is not None]  # (entry, dims, spot)
        scored.sort(key=lambda r: (r[0].top_state is not None, r[0].composite_score), reverse=True)

        # 第二段：对排名靠前的 K 支补抓期权，重算仓位与状态
        enrich_sem = asyncio.Semaphore(ENRICH_CONCURRENCY)
        top = scored[:ENRICH_TOP_K]
        enriched = await asyncio.gather(
            *[_enrich_symbol(e, d, sp, enrich_sem) for (e, d, sp) in top]
        )

    entries = list(enriched) + [e for (e, _, _) in scored[ENRICH_TOP_K:]]
    ranked = _rank(entries)[:limit]
    enriched_states = sum(1 for e in enriched if e.top_state and e.top_state.key in
                          ("institution_accumulation", "smart_money"))

    logger.info("scan_leaderboard_computed", source=source, universe=len(symbols),
                scanned=len(entries), enriched=len(top), option_states=enriched_states,
                returned=len(ranked))

    return LeaderboardResponse(
        status="ready",
        as_of=to_date,
        computed_at=now.isoformat(timespec="seconds"),
        universe_source=source,
        universe_size=len(symbols),
        scanned=len(entries),
        note=f"4 维初筛全 universe，前 {ENRICH_TOP_K} 支补抓期权确认仓位；点进详情看完整五维",
        entries=ranked,
    )
