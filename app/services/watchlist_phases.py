"""自选股列表的中枢阶段标签：给每只自选标的算一下"现在走到哪一步"。

不是新算法——直接复用 app/services/chan/pivot_phase.py 已有的判定，对每只
标的拉一段日线跑一遍缠论分析，取 result.pivot_phase 就是答案。单只标的拉
K 线/算失败（行情源限流、代码有误、结构还没成形）不影响其他标的，返回该
条目的 phase 为 None，前端就不显示标签，不强行凑一个假状态。

并发量控制沿用 signal_radar 的思路（见 app/services/signal_radar/service.py
的 _SCAN_CONCURRENCY）：自选列表通常没有信号雷达扫全市场那么多标的，用一个
更宽松的并发上限即可。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

from redis.asyncio import Redis

from app.core.logging import logger
from app.services.chan.analyzer import ChanAnalyzer
from app.services.skills.kline import fetch_kline

_analyzer = ChanAnalyzer()

# 可见窗口天数，与 iOS 详情页默认起点（近 365 天）保持一致——否则自选标签和
# 点进详情页看到的阶段会对不上（同一只票、同一天，仅因为窗口不同算出两个答案）。
_VISIBLE_DAYS = 365
# 窗口锚定所需的 warmup 天数，与 chan.py 的日线口径一致：在可见起点之前多取一段
# K 线一起送入缠论消除左边界依赖，再裁剪回可见窗口。
_WARMUP_DAYS = 180
# 自选列表规模通常远小于信号雷达扫的全市场 universe，给一个更宽松的并发上限。
_CONCURRENCY = 12


@dataclass
class WatchlistPhase:
    market: str
    symbol: str
    phase: str | None
    phase_label: str | None


async def _phase_for_symbol(
    market: str, symbol: str, *, user_id: int, end_date: str, redis: Redis, sem: asyncio.Semaphore,
) -> WatchlistPhase:
    async with sem:
        visible_from = (date.fromisoformat(end_date) - timedelta(days=_VISIBLE_DAYS)).isoformat()
        anchor_start = (date.fromisoformat(visible_from) - timedelta(days=_WARMUP_DAYS)).isoformat()
        try:
            bars = await fetch_kline(
                user_id=user_id, symbol=symbol, start_date=anchor_start,
                end_date=end_date, freq="daily", redis=redis,
            )
        except Exception as e:  # noqa: BLE001 单只失败不影响自选列表里的其他标的
            logger.warning("watchlist_phase_kline_failed", symbol=symbol, error=str(e))
            return WatchlistPhase(market=market, symbol=symbol, phase=None, phase_label=None)

        if not bars:
            return WatchlistPhase(market=market, symbol=symbol, phase=None, phase_label=None)

        try:
            result = _analyzer.analyze(symbol, bars, lang="zh", visible_from=visible_from)
        except Exception as e:  # noqa: BLE001 同上
            logger.warning("watchlist_phase_analyze_failed", symbol=symbol, error=str(e))
            return WatchlistPhase(market=market, symbol=symbol, phase=None, phase_label=None)

        if result.pivot_phase is None:
            return WatchlistPhase(market=market, symbol=symbol, phase=None, phase_label=None)
        return WatchlistPhase(market=market, symbol=symbol,
                               phase=result.pivot_phase.phase, phase_label=result.pivot_phase.phase_label)


async def fetch_phase_labels(
    items: list[tuple[str, str]], *, user_id: int, redis: Redis,
) -> list[WatchlistPhase]:
    """批量算一遍自选列表里每只标的当前的中枢阶段。

    items: [(market, symbol), ...]。并发执行，互不影响彼此的成败。
    """
    if not items:
        return []
    end_date = date.today().isoformat()
    sem = asyncio.Semaphore(_CONCURRENCY)
    return await asyncio.gather(*(
        _phase_for_symbol(market, symbol, user_id=user_id, end_date=end_date, redis=redis, sem=sem)
        for market, symbol in items
    ))
