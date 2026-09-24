"""次级别确认编排：拉次级别 K 线 → 缠论分析 → 与大级别结果联动判定。

日线配 30 分钟、周线配日线（见 sub_level.LEVEL_PAIRS）。供 /chan/sub-level 接口与
信号雷达复用。次级别取数失败或数据为空时降级为「不可用」，不抛异常——次级别是附加
信息，不能拖垮大级别分析。
"""
from __future__ import annotations

from datetime import date, timedelta

from redis.asyncio import Redis

from app.core.logging import logger
from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.chan.sub_level import LEVEL_PAIRS, SubLevelResult, build_sub_level
from app.services.skills.kline import fetch_kline

_analyzer = ChanAnalyzer()


async def analyze_sub_level(
    symbol: str,
    end_date: str,
    daily: ChanAnalysisResult,
    *,
    user_id: int | None = None,
    redis: Redis | None = None,
    lang: str = "zh",
    parent_freq: str = "daily",
) -> SubLevelResult:
    """以 end_date 为止取次级别 K 线分析，并与大级别结果（daily 参数）联动判定。"""
    pair = LEVEL_PAIRS.get(parent_freq, LEVEL_PAIRS["daily"])
    start = (date.fromisoformat(end_date[:10]) - timedelta(days=pair.fetch_days)).isoformat()
    try:
        bars = await fetch_kline(user_id, symbol, start, end_date, pair.child, redis=redis)
    except Exception as exc:  # noqa: BLE001  次级别失败只降级，不影响大级别
        logger.warning("sub_level_kline_failed", symbol=symbol, freq=pair.child, error=str(exc))
        bars = []

    sub = _analyzer.analyze(symbol, bars, lang=lang, freq=pair.child) if bars else None
    return build_sub_level(daily, sub, lang, parent_freq=pair.parent)
