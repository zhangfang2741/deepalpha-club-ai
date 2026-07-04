"""机构建仓榜：扫描 universe，用 4 个 FMP 快接口排名（跳过期权）。

两段式：榜单负责「筛选」（不含仓位/期权），用户点进详情页跑「完整五维」确认。
排名用与详情页一致的综合分（缺失维度按中性计入）——仓位对所有股票同权重缺失，
不影响相对排序。
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
    SCAN_CONCURRENCY,
    SCAN_TOP_N,
    SCAN_UNIVERSE_FALLBACK,
)
from app.services.institutional_signals.dimensions import (
    compute_confirmation,
    compute_expectation,
    compute_fundamental,
    compute_participation,
    unavailable_dimension,
)
from app.services.institutional_signals.fetchers import (
    fetch_earnings,
    fetch_grades_historical,
    fetch_insider_statistics,
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


async def _score_symbol(
    client: httpx.AsyncClient, symbol: str, sem: asyncio.Semaphore,
    from_date: str, to_date: str,
) -> LeaderboardEntry | None:
    """单支扫描评分（4 个 FMP 维度，仓位置为 unavailable）。"""
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
        "positioning": unavailable_dimension("positioning", "榜单不含期权，点进详情页查看"),
        "participation": compute_participation(prices),
        "fundamental": compute_fundamental(earnings),
        "confirmation": compute_confirmation(insider),
    }
    coverage = _coverage(dims)
    if coverage == 0:
        return None  # 全无数据，不入榜

    states = [s for s in derive_states(dims) if s.key != "neutral"]
    bullish = [s for s in states if s.key in _BULLISH_STATES]
    top_state = max(bullish, key=lambda s: s.stars) if bullish else None
    name = (profile or {}).get("companyName") or (profile or {}).get("name") or symbol

    return LeaderboardEntry(
        symbol=symbol,
        name=name,
        composite_score=_composite_score(dims),
        coverage=coverage,
        confidence=_confidence(coverage),
        top_state=top_state,
        states=states,
        dimension_scores={k: d.score for k, d in dims.items() if d.status != "unavailable"},
    )


def _rank(entries: list[LeaderboardEntry]) -> list[LeaderboardEntry]:
    """有偏多状态的优先，其次综合分——纯函数，便于单测。"""
    return sorted(
        entries,
        key=lambda e: (e.top_state is not None, e.composite_score),
        reverse=True,
    )


async def scan_leaderboard(limit: int = SCAN_TOP_N) -> LeaderboardResponse:
    """扫描 universe 并返回机构建仓榜前 N（在后台任务里调用，不阻塞请求）。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    from_date = (today - datetime.timedelta(days=_PRICE_LOOKBACK_DAYS)).isoformat()
    to_date = today.isoformat()
    sem = asyncio.Semaphore(SCAN_CONCURRENCY)

    async with httpx.AsyncClient(timeout=15) as client:
        symbols = await fetch_sp500_symbols(client)
        source = "sp500"
        if not symbols:
            symbols = list(SCAN_UNIVERSE_FALLBACK)
            source = "fallback"

        results = await asyncio.gather(
            *[_score_symbol(client, s, sem, from_date, to_date) for s in symbols]
        )

    entries = [e for e in results if e is not None]
    ranked = _rank(entries)[:limit]

    logger.info("scan_leaderboard_computed", source=source,
                universe=len(symbols), scanned=len(entries), returned=len(ranked))

    return LeaderboardResponse(
        status="ready",
        as_of=to_date,
        computed_at=now.isoformat(timespec="seconds"),
        universe_source=source,
        universe_size=len(symbols),
        scanned=len(entries),
        note="榜单基于 4 个 FMP 维度（不含期权仓位），点进详情页查看完整五维",
        entries=ranked,
    )
