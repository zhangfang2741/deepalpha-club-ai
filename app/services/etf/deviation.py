"""ETF 错杀分计算服务（历史自身对比）。

算法：
  两个时间窗口：
    recent_days（近期，默认 30 交易日）
    hist_days  （历史基准，默认 365 交易日，含近期）

  对每只 ETF i：
    hist_panic_avg  = mean(intensity for ALL hist_days where FG < 45)
    recent_panic_avg = mean(intensity for recent_days where FG < 45)
    错杀分 = recent_panic_avg - hist_panic_avg

  错杀分 << 0 → 近期恐慌期表现远差于自身历史 → 被错杀（潜在机会）
  错杀分 >> 0 → 近期恐慌期表现远好于自身历史 → 异常强势
"""

from typing import Dict, List, Optional, Tuple

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.etf import (
    DeviationScoreResponse,
    ETFDeviationScore,
    SectorDeviationGroup,
)
from app.schemas.fear_greed import FearGreedPoint, FearGreedSnapshot
from app.services.etf.constants import CHINESE_NAMES, ETF_LIBRARY


def compute_historical_scores(
    symbol_intensity: Dict[str, Dict[str, float]],
    fg_by_date: Dict[str, float],
    recent_dates: set,
    panic_threshold: float = 45.0,
    greed_threshold: float = 55.0,
) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float], int, int]]:
    """计算每只 ETF 的错杀分（近期 vs 全历史自身基准对比）。

    Args:
        symbol_intensity: {symbol: {date: intensity}}
        fg_by_date: {date: fg_score}
        recent_dates: 近期日期集合（最后 recent_days 个交易日）
        panic_threshold: FG 低于此值视为恐慌期（默认 45）
        greed_threshold: FG 高于此值视为贪婪期（默认 55）

    Returns:
        {symbol: (panic_score, greed_score, overall_score, recent_panic_days, recent_greed_days)}
        panic_score = recent_panic_avg - hist_panic_avg
        greed_score = recent_greed_avg - hist_greed_avg
    """
    scores: Dict[str, Tuple[Optional[float], Optional[float], Optional[float], int, int]] = {}

    for symbol, intensities in symbol_intensity.items():
        hist_panic: List[float] = []
        hist_greed: List[float] = []
        recent_panic: List[float] = []
        recent_greed: List[float] = []

        for date, intensity in intensities.items():
            if date not in fg_by_date:
                continue
            fg = fg_by_date[date]
            if fg < panic_threshold:
                hist_panic.append(intensity)
                if date in recent_dates:
                    recent_panic.append(intensity)
            elif fg > greed_threshold:
                hist_greed.append(intensity)
                if date in recent_dates:
                    recent_greed.append(intensity)

        def _avg(lst: List[float]) -> Optional[float]:
            return sum(lst) / len(lst) if lst else None

        hist_panic_avg = _avg(hist_panic)
        hist_greed_avg = _avg(hist_greed)
        recent_panic_avg = _avg(recent_panic)
        recent_greed_avg = _avg(recent_greed)

        panic_score: Optional[float] = None
        if recent_panic_avg is not None and hist_panic_avg is not None:
            panic_score = round(recent_panic_avg - hist_panic_avg, 4)

        greed_score: Optional[float] = None
        if recent_greed_avg is not None and hist_greed_avg is not None:
            greed_score = round(recent_greed_avg - hist_greed_avg, 4)

        overall_score: Optional[float] = None
        if panic_score is not None and greed_score is not None:
            overall_score = round((panic_score + greed_score) / 2, 4)

        scores[symbol] = (panic_score, greed_score, overall_score, len(recent_panic), len(recent_greed))

    return scores


def _extract_symbol_intensity_from_heatmap(days: int) -> Dict[str, Dict[str, float]]:
    """从 HeatmapResponse 中提取 symbol_intensity 映射（同步）。

    复用 build_heatmap_data 已有的下载和计算逻辑，固定 granularity='day'。
    """
    from app.services.etf.fetcher import build_heatmap_data

    heatmap = build_heatmap_data(granularity="day", days=days)
    symbol_intensity: Dict[str, Dict[str, float]] = {}
    for sector in heatmap.sectors:
        for etf_row in sector.etfs:
            if etf_row.symbol not in symbol_intensity:
                symbol_intensity[etf_row.symbol] = {}
            for cell in etf_row.cells:
                if cell.intensity is not None:
                    symbol_intensity[etf_row.symbol].setdefault(cell.date, cell.intensity)
    return symbol_intensity


def build_deviation_response(
    symbol_intensity: Dict[str, Dict[str, float]],
    fg_history: List[FearGreedPoint],
    fg_current: FearGreedSnapshot,
    recent_days: int,
    days_hist: int,
) -> DeviationScoreResponse:
    """纯计算函数：将 ETF 强度与 FG 历史合并，生成错杀分响应。

    Args:
        symbol_intensity: {symbol: {date: intensity}}（对应 days_hist 窗口）
        fg_history: Fear & Greed 历史数据列表
        fg_current: 当前 FG 快照（用于填写 fg_score/fg_rating）
        recent_days: 近期窗口交易日数量
        days_hist: 历史基准窗口交易日数量

    Returns:
        DeviationScoreResponse
    """
    fg_by_date: Dict[str, float] = {p.date: p.score for p in fg_history}

    # 从所有出现的交易日中取最新的 recent_days 天作为近期集合
    all_dates = sorted(
        {date for intensities in symbol_intensity.values() for date in intensities}
    )
    recent_dates: set = set(all_dates[-recent_days:]) if len(all_dates) >= recent_days else set(all_dates)

    raw_scores = compute_historical_scores(symbol_intensity, fg_by_date, recent_dates)

    sectors: List[SectorDeviationGroup] = []
    for sector_name, sector_symbols in ETF_LIBRARY.items():
        etf_scores: List[ETFDeviationScore] = []
        for symbol in sector_symbols:
            s = raw_scores.get(symbol)
            if s is not None:
                panic_score, greed_score, overall_score, panic_days, greed_days = s
            else:
                panic_score = greed_score = overall_score = None
                panic_days = greed_days = 0
            etf_scores.append(
                ETFDeviationScore(
                    symbol=symbol,
                    name=CHINESE_NAMES.get(symbol, symbol),
                    sector=sector_name,
                    panic_score=panic_score,
                    panic_days=panic_days,
                    greed_score=greed_score,
                    greed_days=greed_days,
                    overall_score=overall_score,
                )
            )

        panic_vals = [e.panic_score for e in etf_scores if e.panic_score is not None]
        greed_vals = [e.greed_score for e in etf_scores if e.greed_score is not None]
        overall_vals = [e.overall_score for e in etf_scores if e.overall_score is not None]

        sectors.append(
            SectorDeviationGroup(
                sector=sector_name,
                avg_panic_score=round(sum(panic_vals) / len(panic_vals), 4) if panic_vals else None,
                avg_greed_score=round(sum(greed_vals) / len(greed_vals), 4) if greed_vals else None,
                avg_overall_score=round(sum(overall_vals) / len(overall_vals), 4) if overall_vals else None,
                etfs=etf_scores,
            )
        )

    return DeviationScoreResponse(
        days=recent_days,
        days_hist=days_hist,
        fg_score=fg_current.score,
        fg_rating=fg_current.rating,
        sectors=sectors,
    )


async def compute_deviation_scores(
    redis: Redis,
    days: int = 30,
    days_hist: int = 365,
) -> DeviationScoreResponse:
    """主函数：获取 ETF 强度和 FG 历史，计算错杀分响应。

    Args:
        redis: Redis 客户端（用于 FG 缓存）
        days: 近期窗口交易日数量
        days_hist: 历史基准窗口交易日数量

    Returns:
        DeviationScoreResponse
    """
    from app.services.fear_greed import fear_greed_service

    logger.info("etf_deviation_compute_start", days=days, days_hist=days_hist)

    fg_data = await fear_greed_service.get_history(redis)
    symbol_intensity = _extract_symbol_intensity_from_heatmap(days_hist)

    logger.info(
        "etf_deviation_data_fetched",
        etf_count=len(symbol_intensity),
        fg_history_count=len(fg_data.history),
    )

    return build_deviation_response(
        symbol_intensity=symbol_intensity,
        fg_history=fg_data.history,
        fg_current=fg_data.current,
        recent_days=days,
        days_hist=days_hist,
    )
