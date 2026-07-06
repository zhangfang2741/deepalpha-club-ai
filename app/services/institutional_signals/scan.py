"""机构建仓榜：初筛挑候选 + 完整计算定榜。

- 第一段（初筛）：全 universe 用 4 个 FMP 快接口排名（跳过期权），只用来挑候选。
- 第二段（定榜）：对初筛靠前的 top-N 走**与详情页完全相同**的 compute_institutional_signals
  （含期权 + 快照 deltas），并把完整报告预写进详情缓存——使点进详情页的分数与榜单完全一致。
"""
import asyncio
import datetime

import httpx

from app.cache.client import current_redis
from app.core.logging import logger
from app.db.session import AsyncSessionFactory
from app.schemas.institutional_signals import (
    InstitutionalSignalReport,
    LeaderboardEntry,
    LeaderboardResponse,
)
from app.services.institutional_signals.calculator import (
    _composite_score,
    _confidence,
    _coverage,
    compute_institutional_signals,
)
from app.services.institutional_signals.constants import (
    FINALIZE_CONCURRENCY,
    LEADERBOARD_DETAIL_CACHE_TTL,
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
    unavailable_dimension,
)
from app.services.institutional_signals.fetchers import (
    fetch_earnings,
    fetch_grades_historical,
    fetch_insider_statistics,
    fetch_nasdaq100_symbols,
    fetch_price_history,
    fetch_price_target_summary,
    fetch_profile,
    fetch_sp500_symbols,
)
from app.services.institutional_signals.report_cache import report_cache_key, report_cache_version
from app.services.institutional_signals.states import derive_states

_PRICE_LOOKBACK_DAYS = 60
# 只把这些「偏多/机会型」状态视为上榜理由（撤退等看空状态不进建仓榜）
_BULLISH_STATES = {
    "institution_accumulation", "expectation_upgrade",
    "breakout_confirmation", "fundamental_turn", "smart_money",
}


def _top_state(states: list):
    """从状态列表里挑出最强的偏多状态（星级高、买入排序靠前）作为 top_state。"""
    bullish = [s for s in states if s.key in _BULLISH_STATES]
    return max(bullish, key=lambda s: (s.stars, -(s.buy_rank or 9))) if bullish else None


def _build_entry(symbol: str, name: str, dims: dict) -> LeaderboardEntry:
    """由维度字典构造榜单行（综合分/状态/top_state）——初筛阶段用。"""
    states = [s for s in derive_states(dims) if s.key != "neutral"]
    return LeaderboardEntry(
        symbol=symbol,
        name=name,
        composite_score=_composite_score(dims),
        coverage=_coverage(dims),
        confidence=_confidence(_coverage(dims)),
        top_state=_top_state(states),
        states=states,
        dimension_scores={k: d.score for k, d in dims.items() if d.status != "unavailable"},
    )


def _entry_from_report(report: InstitutionalSignalReport) -> LeaderboardEntry:
    """由完整报告构造榜单行——与详情页同源，保证综合分/五维分一致。"""
    dims = {d.key: d for d in report.dimensions}
    states = [s for s in report.states if s.key != "neutral"]
    return LeaderboardEntry(
        symbol=report.symbol,
        name=report.name,
        composite_score=report.composite_score,
        coverage=report.coverage,
        confidence=report.confidence,
        top_state=_top_state(states),
        states=states,
        dimension_scores={k: d.score for k, d in dims.items() if d.status != "unavailable"},
    )


async def _score_symbol(
    client: httpx.AsyncClient, symbol: str, sem: asyncio.Semaphore,
    from_date: str, to_date: str,
) -> tuple[LeaderboardEntry, dict, float] | None:
    """初筛评分（4 个 FMP 维度，仓位 unavailable）；返回 (entry, dims, spot)。"""
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
        "positioning": unavailable_dimension("positioning", "榜单初筛不含期权，定榜时补齐/点进详情查看"),
        "participation": compute_participation(prices),
        "fundamental": compute_fundamental(earnings),
        "confirmation": compute_confirmation(insider),
    }
    if _coverage(dims) == 0:
        return None  # 全无数据，不入榜

    name = (profile or {}).get("companyName") or (profile or {}).get("name") or symbol
    spot = prices[-1]["close"] if prices else 0.0
    return _build_entry(symbol, name, dims), dims, spot


async def _finalize_symbol(symbol: str, sem: asyncio.Semaphore, version: str) -> LeaderboardEntry | None:
    """定榜：对单支走完整五维计算（同详情页），并把报告预写进详情缓存。"""
    async with sem:
        session = AsyncSessionFactory()
        try:
            report = await compute_institutional_signals(symbol, session=session)
        except Exception as e:
            logger.warning("leaderboard_finalize_failed", symbol=symbol, error=str(e))
            return None
        finally:
            await session.close()

    # 预写详情缓存：使前端点进详情命中同一份数据，分数与榜单完全一致
    redis = current_redis()
    if redis is not None:
        try:
            await redis.set(
                report_cache_key(symbol, version),
                report.model_dump_json(),
                ex=LEADERBOARD_DETAIL_CACHE_TTL,
            )
        except Exception as e:
            logger.warning("leaderboard_detail_cache_write_failed", symbol=symbol, error=str(e))

    return _entry_from_report(report)


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

        # 第一段（初筛）：全 universe 4 维评分，只用来挑候选
        results = await asyncio.gather(
            *[_score_symbol(client, s, sem, from_date, to_date) for s in symbols]
        )
        scored = [r for r in results if r is not None]  # (entry, dims, spot)
        scored.sort(key=lambda r: (r[0].top_state is not None, r[0].composite_score), reverse=True)

    # 扫了整个 universe 却一支都没评出分 → 不是「今日无热门」，而是行情数据源整体不可用
    # （FMP key 失效/限流/未生效），据此明确区分，避免前端笼统显示「榜单暂不可用」
    data_source_down = len(symbols) > 0 and len(scored) == 0
    if data_source_down:
        note = (f"机构资金数据源暂不可用：扫描了 {len(symbols)} 支但无一取到数据，"
                "疑似行情接口未配置/失效/限流，请稍后重试或检查数据源配置。")
        logger.info("scan_leaderboard_computed", source=source, universe=len(symbols),
                    scanned=0, returned=0, data_source_down=True)
        return LeaderboardResponse(
            status="unavailable", as_of=to_date,
            computed_at=now.isoformat(timespec="seconds"),
            universe_source=source, universe_size=len(symbols), scanned=0,
            note=note, entries=[],
        )

    # 第二段（定榜）：对初筛靠前的 top-N 走完整五维计算（同详情页）并预写详情缓存
    candidates = [entry.symbol for (entry, _, _) in scored[:limit]]
    version = report_cache_version()
    fin_sem = asyncio.Semaphore(FINALIZE_CONCURRENCY)
    finalized = await asyncio.gather(*[_finalize_symbol(s, fin_sem, version) for s in candidates])
    entries = [e for e in finalized if e is not None]
    ranked = _rank(entries)[:limit]

    note = "榜单展示的标的走完整五维计算，与详情页同口径；点进详情数字一致"
    logger.info("scan_leaderboard_computed", source=source, universe=len(symbols),
                screened=len(scored), finalized=len(entries), returned=len(ranked),
                data_source_down=False)

    return LeaderboardResponse(
        status="ready",
        as_of=to_date,
        computed_at=now.isoformat(timespec="seconds"),
        universe_source=source,
        universe_size=len(symbols),
        scanned=len(entries),
        note=note,
        entries=ranked,
    )
