"""次级别确认编排：拉 30 分钟 K 线 → 缠论分析 → 与日线结果联动判定。

供 /chan/sub-level 接口与信号雷达复用。30 分钟取数失败或数据为空时降级为
「不可用」，不抛异常——次级别是附加信息，不能拖垮日线分析。
"""
from __future__ import annotations

from datetime import date, timedelta

from redis.asyncio import Redis

from app.core.logging import logger
from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.chan.sub_level import SubLevelResult, build_sub_level
from app.services.skills.kline import fetch_kline

# 30 分钟取数窗口：约 27 个交易日，足够形成次级别的笔与中枢；Yahoo 分钟线上限 60 天
_SUB_WINDOW_DAYS = 40

_analyzer = ChanAnalyzer()


async def analyze_sub_level(
    symbol: str,
    end_date: str,
    daily: ChanAnalysisResult,
    *,
    user_id: int | None = None,
    redis: Redis | None = None,
    lang: str = "zh",
) -> SubLevelResult:
    """以 end_date 为止取 30 分钟 K 线分析，并与日线结果联动判定。"""
    start = (date.fromisoformat(end_date[:10]) - timedelta(days=_SUB_WINDOW_DAYS)).isoformat()
    try:
        bars = await fetch_kline(user_id, symbol, start, end_date, "30min", redis=redis)
    except Exception as exc:  # noqa: BLE001  次级别失败只降级，不影响日线
        logger.warning("sub_level_kline_failed", symbol=symbol, error=str(exc))
        bars = []

    sub = _analyzer.analyze(symbol, bars, lang=lang, freq="30min") if bars else None
    return build_sub_level(daily, sub, lang)
