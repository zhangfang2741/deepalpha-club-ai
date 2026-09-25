"""次级别确认编排：拉次级别 K 线 → 缠论分析 → 与大级别结果联动判定。

日线配 30 分钟、周线配日线（见 sub_level.LEVEL_PAIRS）。供 /chan/sub-level 接口与
信号雷达复用。次级别取数失败或数据为空时降级为「不可用」，不抛异常——次级别是附加
信息，不能拖垮大级别分析。
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, timedelta

from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.chan import SignalOut, SubLevelResponse
from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.chan.signals import Signal
from app.services.chan.sub_level import LEVEL_PAIRS, SubLevelResult, build_sub_level
from app.services.skills.kline import fetch_kline
from app.utils.market import normalize as normalize_symbol

_analyzer = ChanAnalyzer()


async def _fetch_sub_analysis(
    symbol: str,
    end_date: str,
    *,
    parent_freq: str,
    user_id: int | None,
    redis: Redis | None,
    lang: str,
    use_cache: bool = True,
) -> ChanAnalysisResult | None:
    """只取次级别 K 线并分析，不做联动判定。

    供 analyze_sub_level 与 current_sub_level 复用，后者借此把次级别取数与大级别
    取数并发起来，而不是等大级别取完再取次级别。
    """
    pair = LEVEL_PAIRS.get(parent_freq, LEVEL_PAIRS["daily"])
    start = (date.fromisoformat(end_date[:10]) - timedelta(days=pair.fetch_days)).isoformat()
    try:
        bars = await fetch_kline(user_id, symbol, start, end_date, pair.child, redis=redis,
                                 use_cache=use_cache)
    except Exception as exc:  # noqa: BLE001  次级别失败只降级，不影响大级别
        logger.warning("sub_level_kline_failed", symbol=symbol, freq=pair.child, error=str(exc))
        bars = []
    return _analyzer.analyze(symbol, bars, lang=lang, freq=pair.child) if bars else None


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
    sub = await _fetch_sub_analysis(
        symbol, end_date, parent_freq=parent_freq, user_id=user_id, redis=redis, lang=lang,
    )
    return build_sub_level(daily, sub, lang, parent_freq=pair.parent)


# ---------------------------------------------------------------------------
# 统一口径 + 结论缓存：雷达气泡与详情页读同一份次级别结论
# ---------------------------------------------------------------------------

# 大级别固定取数窗口（自然日）：次级别结论描述的是「现在」，与详情页所选日期范围无关。
# 日线约 450 天（与雷达扫描同量级，足够预热），周线约 4 年。
_PARENT_LOOKBACK_DAYS = {"daily": 450, "weekly": 1500}

# 结论缓存时长：长于雷达盘中刷新间隔（默认 30 分钟），保证刷新写入的结论在下一轮
# 刷新前一直有效——详情页读到的就是气泡上那一份。
SUB_LEVEL_CACHE_TTL = 3600


def signal_out(sig: Signal) -> SignalOut:
    """内部 Signal → 接口 SignalOut（分析详情与次级别共用）。"""
    return SignalOut(
        type=sig.type,
        label=sig.label,
        time=sig.time,
        price=sig.price,
        strength=sig.strength,
        is_buy=sig.is_buy,
        description=sig.description,
        confirmed=sig.confirmed,
        price_ratio=sig.divergence.price_ratio if sig.divergence else None,
        volume_ratio=sig.divergence.volume_ratio if sig.divergence else None,
        length_ratio=sig.divergence.length_ratio if sig.divergence else None,
    )


def canonical_end(end_date: str | None, *, today: date | None = None) -> str:
    """截止日统一到服务器当天：客户端本地日期可能领先 UTC 一天（东八区），与雷达对齐。"""
    today_s = (today or date.today()).isoformat()
    if not end_date:
        return today_s
    return min(end_date[:10], today_s)


def _canonical_symbol(symbol: str) -> str:
    """代码归一化（600519 / 600519.SS、0700.HK / 00700 视为同一只），供缓存键使用。"""
    try:
        market, clean = normalize_symbol(symbol)
        return f"{market.value}:{clean}"
    except Exception:  # noqa: BLE001 识别不了就原样大写
        return symbol.strip().upper()


def _cache_key(symbol: str, parent_freq: str, end: str, lang: str) -> str:
    return f"chan_sub_level:{_canonical_symbol(symbol)}:{parent_freq}:{end}:{lang}"


def to_response(symbol: str, sub: SubLevelResult) -> SubLevelResponse:
    """内部判定结果 → 接口响应（缓存与返回都用这一形态）。"""
    return SubLevelResponse(
        symbol=symbol,
        parent_freq=sub.parent_freq,
        daily_bias=sub.daily_bias,
        daily_bias_label=sub.daily_bias_label,
        sub_freq=sub.sub_freq,
        verdict=sub.verdict,
        verdict_label=sub.verdict_label,
        detail=sub.detail,
        recent_signals=[signal_out(sig) for sig in sub.recent_signals],
    )


async def current_sub_level(
    symbol: str,
    parent_freq: str = "daily",
    *,
    end_date: str | None = None,
    user_id: int | None = None,
    redis: Redis | None = None,
    lang: str = "zh",
    refresh: bool = False,
    fetch_parent: Callable[[str, str, str], Awaitable[list[dict]]] | None = None,
    use_cache: bool = True,
) -> SubLevelResponse:
    """当前次级别结论（雷达与详情页的唯一入口）：固定口径计算 + 按结论缓存。

    - 口径固定：大级别窗口 = 截止日往前 _PARENT_LOOKBACK_DAYS，不随调用方日期范围变化；
      截止日统一到服务器当天。同样的K线 → 同样的结论。
    - 结论缓存：按（归一化代码, 大级别, 截止日, 语言）缓存完整结果。雷达刷新传 refresh=True
      重算并覆盖，详情页优先读缓存——气泡上的共振与点进去看到的是同一次计算。
    - fetch_parent：大级别取数函数（接口层传入以把数据源错误转成 HTTP 错误），默认 fetch_kline。
    - use_cache=False：详情页现拉现算——不读结论缓存、次级别K线也不读缓存（盘中要看到最新
      的 30 分钟K线），算出的新结论仍写回缓存，雷达下次读到的就是这份。
    """
    end = canonical_end(end_date)
    key = _cache_key(symbol, parent_freq, end, lang)
    if redis is not None and not refresh and use_cache:
        cached = await get_json(redis, key)
        if cached:
            try:
                return SubLevelResponse.model_validate(cached)
            except Exception as exc:  # noqa: BLE001 缓存结构过期当未命中
                logger.warning("sub_level_cache_invalid", key=key, error=str(exc))

    start = (date.fromisoformat(end) - timedelta(days=_PARENT_LOOKBACK_DAYS.get(parent_freq, 450))).isoformat()

    async def _fetch_parent_bars() -> list[dict]:
        if fetch_parent is not None:
            return await fetch_parent(start, end, parent_freq)
        return await fetch_kline(user_id, symbol, start, end, parent_freq, redis=redis, use_cache=use_cache)

    # 大级别与次级别取数互相独立，并发发起——原先是「等大级别取完+分析完才开始取次级别」，
    # 串行等待白白多花一轮网络延迟，是详情页打开次级别徽标慢的主因之一。
    bars, sub_analysis = await asyncio.gather(
        _fetch_parent_bars(),
        _fetch_sub_analysis(symbol, end, parent_freq=parent_freq, user_id=user_id, redis=redis, lang=lang,
                            use_cache=use_cache),
    )
    parent = _analyzer.analyze(symbol, bars, lang=lang, freq=parent_freq)
    pair = LEVEL_PAIRS.get(parent_freq, LEVEL_PAIRS["daily"])
    sub = build_sub_level(parent, sub_analysis, lang, parent_freq=pair.parent)
    resp = to_response(symbol, sub)
    if redis is not None:
        await set_json(redis, key, resp.model_dump(), expire=SUB_LEVEL_CACHE_TTL)
    return resp
