"""机构资金信号编排：symbol → InstitutionalSignalReport。

Phase 1：Expectation + Participation（FMP 全覆盖）。
Positioning / Fundamental / Confirmation 先占位 unavailable，后续 Phase 接入。
"""
import asyncio
import datetime
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.schemas.institutional_signals import DimensionScore, InstitutionalSignalReport
from app.services.institutional_signals.constants import DIMENSION_WEIGHTS
from app.services.institutional_signals.deltas import iv_rank, pct_change, value_days_ago
from app.services.institutional_signals.dimensions import (
    compute_confirmation,
    compute_expectation,
    compute_fundamental,
    compute_participation,
    compute_positioning,
)
from app.services.institutional_signals.fetchers import (
    fetch_analyst_estimate,
    fetch_earnings,
    fetch_grades_historical,
    fetch_insider_statistics,
    fetch_option_metrics,
    fetch_price_history,
    fetch_price_target_summary,
    fetch_profile,
)
from app.services.institutional_signals.snapshot import get_snapshot_history, upsert_snapshot
from app.services.institutional_signals.states import derive_states

# 快照相关窗口
_SNAPSHOT_HISTORY_DAYS = 365  # 读取一年历史算 IV Rank
_OI_CHANGE_DAYS = 5           # OI 变化对比窗口
_REVISION_DAYS = 90           # 预期修正对比窗口


def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

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


async def _snapshot_deltas(
    session: AsyncSession, symbol: str, today: str,
    pt_summary: Optional[dict], estimate: Optional[dict], option_metrics: Optional[dict],
) -> dict:
    """写入当日快照并从历史算出变化率/排名；DB 失败时返回空 dict（best-effort）。"""
    metrics = {
        "eps_estimate": _f((estimate or {}).get("epsAvg") or (estimate or {}).get("estimatedEpsAvg")),
        "revenue_estimate": _f((estimate or {}).get("revenueAvg") or (estimate or {}).get("estimatedRevenueAvg")),
        "price_target_avg": _f((pt_summary or {}).get("lastMonthAvgPriceTarget")),
        "call_oi": (option_metrics or {}).get("call_oi"),
        "put_oi": (option_metrics or {}).get("put_oi"),
        "call_vol": (option_metrics or {}).get("call_vol"),
        "put_vol": (option_metrics or {}).get("put_vol"),
        "atm_iv": (option_metrics or {}).get("atm_iv"),
    }
    try:
        await upsert_snapshot(session, symbol, today, metrics)
        history = await get_snapshot_history(session, symbol, _SNAPSHOT_HISTORY_DAYS)
    except Exception as e:
        logger.warning("snapshot_capture_failed", symbol=symbol, error=str(e))
        return {}

    iv_hist = [s.atm_iv for s in history]
    oi_pts = [(s.snapshot_date, float(s.call_oi) if s.call_oi is not None else None) for s in history]
    eps_pts = [(s.snapshot_date, s.eps_estimate) for s in history]
    rev_pts = [(s.snapshot_date, s.revenue_estimate) for s in history]

    return {
        "iv_rank_value": iv_rank(metrics["atm_iv"], iv_hist),
        "oi_change_pct": pct_change(metrics["call_oi"], value_days_ago(oi_pts, _OI_CHANGE_DAYS)),
        "eps_revision_pct": pct_change(metrics["eps_estimate"], value_days_ago(eps_pts, _REVISION_DAYS)),
        "revenue_revision_pct": pct_change(metrics["revenue_estimate"], value_days_ago(rev_pts, _REVISION_DAYS)),
    }


async def compute_institutional_signals(
    symbol: str, session: Optional[AsyncSession] = None
) -> InstitutionalSignalReport:
    """拉取数据、打分、推导状态，返回完整报告。

    传入 session 时会写入当日快照并用历史算出 IV Rank / OI 变化 / EPS 修正等变化率信号。
    """
    symbol = symbol.upper().strip()
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=_PRICE_LOOKBACK_DAYS)).isoformat()
    to_date = today.isoformat()

    async with httpx.AsyncClient(timeout=15) as client:
        profile, pt_summary, grades, prices, earnings, insider, estimate = await asyncio.gather(
            fetch_profile(client, symbol),
            fetch_price_target_summary(client, symbol),
            fetch_grades_historical(client, symbol),
            fetch_price_history(client, symbol, from_date, to_date),
            fetch_earnings(client, symbol),
            fetch_insider_statistics(client, symbol),
            fetch_analyst_estimate(client, symbol),
        )

    # 期权仓位需现价定位 ATM——用最近收盘价，yfinance 同步拉取放线程池
    spot = prices[-1]["close"] if prices else 0.0
    option_metrics = await asyncio.to_thread(fetch_option_metrics, symbol, spot) if spot else None

    # 快照库：写当日 + 读历史算变化率（DB 不可用时为空，回退到水平口径）
    deltas = await _snapshot_deltas(session, symbol, to_date, pt_summary, estimate, option_metrics) if session else {}

    dims: dict[str, DimensionScore] = {
        "expectation": compute_expectation(
            pt_summary, grades,
            eps_revision_pct=deltas.get("eps_revision_pct"),
            revenue_revision_pct=deltas.get("revenue_revision_pct"),
        ),
        "positioning": compute_positioning(
            option_metrics,
            iv_rank_value=deltas.get("iv_rank_value"),
            oi_change_pct=deltas.get("oi_change_pct"),
        ),
        "participation": compute_participation(prices),
        "fundamental": compute_fundamental(earnings),
        "confirmation": compute_confirmation(insider),
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
