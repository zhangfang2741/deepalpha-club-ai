"""ETF 偏离分计算服务。

计算公式：
  market_avg_t = mean(intensity_j_t for all ETFs on date t)
  dev_i_t      = intensity_i_t - market_avg_t

  按 Fear & Greed 分区：
    FG < 45  → 恐慌期 → panic_score  = mean(dev_i_t)
    FG > 55  → 贪婪期 → greed_score  = mean(dev_i_t)
    overall_score = (panic_score + greed_score) / 2（两者均有值时）

正值 = 高于市场均值（恐慌期=抗跌/避险，贪婪期=强势）
负值 = 低于市场均值（恐慌期=高波，贪婪期=防御）
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


def compute_market_avg(
    symbol_intensity: Dict[str, Dict[str, float]],
) -> Dict[str, float]:
    """计算每个日期所有 ETF 强度的市场均值。

    Args:
        symbol_intensity: {symbol: {date: intensity}}

    Returns:
        market_avg: {date: mean_intensity_across_all_etfs}
    """
    all_dates: set = set()
    for intensities in symbol_intensity.values():
        all_dates.update(intensities.keys())

    market_avg: Dict[str, float] = {}
    for date in all_dates:
        values = [
            symbol_intensity[sym][date]
            for sym in symbol_intensity
            if date in symbol_intensity[sym]
        ]
        if values:
            market_avg[date] = sum(values) / len(values)
    return market_avg


def compute_deviations(
    symbol_intensity: Dict[str, Dict[str, float]],
    market_avg: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    """计算每只 ETF 每日相对市场均值的偏离值。

    Args:
        symbol_intensity: {symbol: {date: intensity}}
        market_avg: {date: mean_intensity}

    Returns:
        deviations: {symbol: {date: deviation}}
    """
    deviations: Dict[str, Dict[str, float]] = {}
    for symbol, intensities in symbol_intensity.items():
        deviations[symbol] = {}
        for date, intensity in intensities.items():
            if date in market_avg:
                deviations[symbol][date] = intensity - market_avg[date]
    return deviations


def compute_scores(
    deviations: Dict[str, Dict[str, float]],
    fg_by_date: Dict[str, float],
    panic_threshold: float = 45.0,
    greed_threshold: float = 55.0,
) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float], int, int]]:
    """计算每只 ETF 的 panic/greed/overall 偏离分。

    Args:
        deviations: {symbol: {date: deviation}}
        fg_by_date: {date: fg_score}
        panic_threshold: FG 低于此值视为恐慌期（默认 45）
        greed_threshold: FG 高于此值视为贪婪期（默认 55）

    Returns:
        scores: {symbol: (panic_score, greed_score, overall_score, panic_days, greed_days)}
    """
    scores: Dict[str, Tuple[Optional[float], Optional[float], Optional[float], int, int]] = {}
    for symbol, date_devs in deviations.items():
        panic_devs: List[float] = []
        greed_devs: List[float] = []

        for date, dev in date_devs.items():
            if date not in fg_by_date:
                continue
            fg = fg_by_date[date]
            if fg < panic_threshold:
                panic_devs.append(dev)
            elif fg > greed_threshold:
                greed_devs.append(dev)

        panic_score: Optional[float] = (
            round(sum(panic_devs) / len(panic_devs), 4) if panic_devs else None
        )
        greed_score: Optional[float] = (
            round(sum(greed_devs) / len(greed_devs), 4) if greed_devs else None
        )
        overall_score: Optional[float] = None
        if panic_score is not None and greed_score is not None:
            overall_score = round((panic_score + greed_score) / 2, 4)

        scores[symbol] = (panic_score, greed_score, overall_score, len(panic_devs), len(greed_devs))
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
    days: int,
) -> DeviationScoreResponse:
    """纯计算函数：将 ETF 强度与 FG 历史合并，生成偏离分响应。

    Args:
        symbol_intensity: {symbol: {date: intensity}}
        fg_history: Fear & Greed 历史数据列表
        fg_current: 当前 FG 快照（用于填写 fg_score/fg_rating）
        days: 分析窗口天数

    Returns:
        DeviationScoreResponse
    """
    fg_by_date: Dict[str, float] = {p.date: p.score for p in fg_history}

    market_avg = compute_market_avg(symbol_intensity)
    deviations = compute_deviations(symbol_intensity, market_avg)
    raw_scores = compute_scores(deviations, fg_by_date)

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
        days=days,
        fg_score=fg_current.score,
        fg_rating=fg_current.rating,
        sectors=sectors,
    )


async def compute_deviation_scores(redis: Redis, days: int = 30) -> DeviationScoreResponse:
    """主函数：获取 ETF 强度和 FG 历史，计算偏离分响应。

    Args:
        redis: Redis 客户端（用于 FG 缓存）
        days: 热力图交易日窗口

    Returns:
        DeviationScoreResponse
    """
    from app.services.fear_greed import fear_greed_service

    logger.info("etf_deviation_compute_start", days=days)

    fg_data = await fear_greed_service.get_history(redis)
    symbol_intensity = _extract_symbol_intensity_from_heatmap(days)

    logger.info(
        "etf_deviation_data_fetched",
        etf_count=len(symbol_intensity),
        fg_history_count=len(fg_data.history),
    )

    return build_deviation_response(
        symbol_intensity=symbol_intensity,
        fg_history=fg_data.history,
        fg_current=fg_data.current,
        days=days,
    )
