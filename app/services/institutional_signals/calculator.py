"""机构资金信号编排：symbol → InstitutionalSignalReport。

Phase 1：Expectation + Participation（FMP 全覆盖）。
Positioning / Fundamental / Confirmation 先占位 unavailable，后续 Phase 接入。
"""
import asyncio
import datetime

import httpx

from app.core.logging import logger
from app.schemas.institutional_signals import DimensionScore, InstitutionalSignalReport
from app.services.institutional_signals.constants import DIMENSION_WEIGHTS
from app.services.institutional_signals.dimensions import (
    compute_expectation,
    compute_participation,
    compute_positioning,
    unavailable_dimension,
)
from app.services.institutional_signals.fetchers import (
    fetch_grades_historical,
    fetch_option_metrics,
    fetch_price_history,
    fetch_price_target_summary,
    fetch_profile,
)
from app.services.institutional_signals.states import derive_states

_PRICE_LOOKBACK_DAYS = 60  # 覆盖 20 交易日窗口 + 余量


def _composite_score(dims: dict[str, DimensionScore]) -> float:
    """全维度加权：缺失维度按中性 50 计入（不剔除），避免半盘信息给出满分结论。"""
    acc = sum(dim.score * DIMENSION_WEIGHTS.get(key, 0.0) for key, dim in dims.items())
    total_w = sum(DIMENSION_WEIGHTS.get(key, 0.0) for key in dims)
    if total_w == 0:
        return 50.0
    return round(acc / total_w, 1)


def _coverage(dims: dict[str, DimensionScore]) -> int:
    """已接入数据的维度数（status 为 ok/partial）。"""
    return sum(1 for dim in dims.values() if dim.status != "unavailable")


def _confidence(coverage: int) -> str:
    """由覆盖度映射置信度标签。"""
    if coverage >= 4:
        return "高"
    if coverage >= 2:
        return "中"
    return "低"


def _headline(composite: float, states: list) -> str:
    top = states[0]
    if top.key == "neutral":
        return f"综合分 {composite:.0f}：暂无显著机构资金信号，建议观望。"
    return f"综合分 {composite:.0f}：{top.emoji} {top.label}——{top.meaning}。"


async def compute_institutional_signals(symbol: str) -> InstitutionalSignalReport:
    """拉取数据、打分、推导状态，返回完整报告。"""
    symbol = symbol.upper().strip()
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=_PRICE_LOOKBACK_DAYS)).isoformat()
    to_date = today.isoformat()

    async with httpx.AsyncClient(timeout=15) as client:
        profile, pt_summary, grades, prices = await asyncio.gather(
            fetch_profile(client, symbol),
            fetch_price_target_summary(client, symbol),
            fetch_grades_historical(client, symbol),
            fetch_price_history(client, symbol, from_date, to_date),
        )

    # 期权仓位需现价定位 ATM——用最近收盘价，yfinance 同步拉取放线程池
    spot = prices[-1]["close"] if prices else 0.0
    option_metrics = await asyncio.to_thread(fetch_option_metrics, symbol, spot) if spot else None

    dims: dict[str, DimensionScore] = {
        "expectation": compute_expectation(pt_summary, grades),
        "positioning": compute_positioning(option_metrics),
        "participation": compute_participation(prices),
        "fundamental": unavailable_dimension("fundamental", "财报超预期/指引待接入 · Phase 3"),
        "confirmation": unavailable_dimension("confirmation", "Insider/13F/ETF Flow 待接入 · Phase 3"),
    }

    states = derive_states(dims)
    composite = _composite_score(dims)
    coverage = _coverage(dims)
    confidence = _confidence(coverage)
    name = (profile or {}).get("companyName") or (profile or {}).get("name") or symbol

    logger.info("institutional_signals_computed", symbol=symbol, composite=composite,
                coverage=coverage, states=[s.key for s in states])

    return InstitutionalSignalReport(
        symbol=symbol,
        name=name,
        as_of=to_date,
        composite_score=composite,
        coverage=coverage,
        confidence=confidence,
        headline=_headline(composite, states),
        dimensions=list(dims.values()),
        states=states,
    )
