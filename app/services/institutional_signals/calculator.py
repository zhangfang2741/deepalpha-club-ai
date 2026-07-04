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
    unavailable_dimension,
)
from app.services.institutional_signals.fetchers import (
    fetch_grades_historical,
    fetch_price_history,
    fetch_price_target_summary,
    fetch_profile,
)
from app.services.institutional_signals.states import derive_states

_PRICE_LOOKBACK_DAYS = 60  # 覆盖 20 交易日窗口 + 余量


def _composite_score(dims: dict[str, DimensionScore]) -> float:
    """按权重加权，剔除 unavailable 维度后重新归一化。"""
    total_w = 0.0
    acc = 0.0
    for key, dim in dims.items():
        if dim.status == "unavailable":
            continue
        w = DIMENSION_WEIGHTS.get(key, 0.0)
        acc += dim.score * w
        total_w += w
    if total_w == 0:
        return 50.0
    return round(acc / total_w, 1)


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

    dims: dict[str, DimensionScore] = {
        "expectation": compute_expectation(pt_summary, grades),
        "positioning": unavailable_dimension("positioning", "期权数据（yfinance）待接入 · Phase 2"),
        "participation": compute_participation(prices),
        "fundamental": unavailable_dimension("fundamental", "财报超预期/指引待接入 · Phase 3"),
        "confirmation": unavailable_dimension("confirmation", "Insider/13F/ETF Flow 待接入 · Phase 3"),
    }

    states = derive_states(dims)
    composite = _composite_score(dims)
    name = (profile or {}).get("companyName") or (profile or {}).get("name") or symbol

    logger.info("institutional_signals_computed", symbol=symbol,
                composite=composite, states=[s.key for s in states])

    return InstitutionalSignalReport(
        symbol=symbol,
        name=name,
        as_of=to_date,
        composite_score=composite,
        headline=_headline(composite, states),
        dimensions=list(dims.values()),
        states=states,
    )
