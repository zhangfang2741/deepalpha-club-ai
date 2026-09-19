"""三地恐慌指数服务：统一美股 VIX / A股 50ETF-QVIX / 港股 VHSI 为同一套 0~100 分数。

数据源：
- us：复用现有 app.services.fear_greed（CNN Fear & Greed，已经是 0~100 分，直接搬字段）。
- cn：akshare `index_option_50etf_qvix`（上证50ETF期权隐含波动率，业内俗称"中国波指"）。
      沪深300版本 `index_option_300index_qvix` 近几个月数据大量缺失/为 0（akshare 该接口
      的已知数据质量问题），弃用，改用数据完整的 50ETF 版本。
- hk：akshare `stock_hk_index_daily_sina(symbol="VHSI")`（恒指波幅指数，港交所官方指标）。

折算规则（_vol_to_score）：VIX/QVIX/VHSI 都是「波动率越高＝越恐慌」，但原始量纲
（10~40 上下）和 CNN 分数（0~100，越高越贪婪）没法直接比。做法是取每个点位在其
「最近一年」窗口内的分位数，分位数越高（处于近一年高位）＝越恐慌＝分数越低——
分数 = 100 − 分位数。这样三地的 0/50/100 都对齐到同一套语义（历史同期相对水位），
可以直接复用 CNN 的 Extreme Fear/Fear/Neutral/Greed/Extreme Greed 五档阈值。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

import akshare as ak
import pandas as pd
from redis.asyncio import Redis

from app.cache.panic_index_cache import get_panic_index_cache, set_panic_index_cache
from app.core.logging import logger
from app.schemas.panic_index import PanicIndexPoint, PanicIndexResponse, PanicIndexSnapshot
from app.services.fear_greed import fear_greed_service

# 分位数窗口：约一年的交易日。窗口内数据不足时用已有的全部历史兜底（见 _vol_to_score）。
_PERCENTILE_WINDOW = 252
# 一周 / 一月对应的交易日回溯步数，与 previous_week/previous_month 语义对齐。
_WEEK_LAG = 5
_MONTH_LAG = 21

_LABELS = {
    "us": "VIX 恐慌贪婪指数",
    "cn": "中国波指 (50ETF QVIX)",
    "hk": "恒指波幅指数 (VHSI)",
}


def _score_to_rating(score: float) -> str:
    """与 app.services.fear_greed._score_to_rating 阈值一致，三地共用同一套五档标签。"""
    if score < 25:
        return "Extreme Fear"
    if score < 45:
        return "Fear"
    if score < 56:
        return "Neutral"
    if score < 76:
        return "Greed"
    return "Extreme Greed"


@dataclass
class _RawPoint:
    date: str
    value: float


def _percentile_rank(window: list[float], target: float) -> float:
    """target 在 window 内的分位（0~100，含等于）。"""
    if not window:
        return 50.0
    less_eq = sum(1 for v in window if v <= target)
    return 100.0 * less_eq / len(window)


def _vol_to_points(raw: list[_RawPoint]) -> list[PanicIndexPoint]:
    """把一串波动率原始值转换成 0~100 恐慌贪婪分数序列（越低越恐慌）。"""
    values = [p.value for p in raw]
    points: list[PanicIndexPoint] = []
    for i, p in enumerate(raw):
        lo = max(0, i - _PERCENTILE_WINDOW + 1)
        window = values[lo:i]  # 不含当天，避免"自己跟自己比"把分位数锁在两端
        pct = _percentile_rank(window, p.value) if window else 50.0
        score = round(100.0 - pct, 1)
        points.append(PanicIndexPoint(
            date=p.date, score=score, rating=_score_to_rating(score), raw_value=p.value,
        ))
    return points


def _snapshot_at(points: list[PanicIndexPoint], lag: int) -> PanicIndexSnapshot:
    """取倒数第 lag+1 个点做「N 天前」快照；序列不够长时退回最早的点。"""
    idx = max(0, len(points) - 1 - lag)
    p = points[idx] if points else None
    if p is None:
        return PanicIndexSnapshot(score=50.0, rating="Neutral")
    return PanicIndexSnapshot(score=p.score, rating=p.rating, raw_value=p.raw_value)


def _fetch_cn_qvix() -> pd.DataFrame:
    return ak.index_option_50etf_qvix()


def _fetch_hk_vhsi() -> pd.DataFrame:
    return ak.stock_hk_index_daily_sina(symbol="VHSI")


async def _build_cn(redis: Redis) -> PanicIndexResponse:
    df = await asyncio.to_thread(_fetch_cn_qvix)
    return await _build_from_vol_df(redis, market="cn", df=df)


async def _build_hk(redis: Redis) -> PanicIndexResponse:
    df = await asyncio.to_thread(_fetch_hk_vhsi)
    return await _build_from_vol_df(redis, market="hk", df=df)


async def _build_from_vol_df(redis: Redis, *, market: str, df: pd.DataFrame) -> PanicIndexResponse:
    raw = sorted(
        (
            _RawPoint(date=str(r["date"])[:10], value=float(r["close"]))
            for _, r in df.dropna(subset=["close"]).iterrows()
            if float(r["close"]) > 0
        ),
        key=lambda p: p.date,
    )
    points = _vol_to_points(raw)

    current = points[-1] if points else PanicIndexPoint(
        date=date.today().isoformat(), score=50.0, rating="Neutral", raw_value=None,
    )
    resp = PanicIndexResponse(
        market=market,
        label=_LABELS[market],
        current=PanicIndexSnapshot(
            score=current.score, rating=current.rating, date=current.date, raw_value=current.raw_value,
        ),
        previous_week=_snapshot_at(points, _WEEK_LAG),
        previous_month=_snapshot_at(points, _MONTH_LAG),
        history=points,
    )
    await set_panic_index_cache(redis, market, resp)
    return resp


async def _build_us(redis: Redis) -> PanicIndexResponse:
    """美股直接搬 CNN Fear & Greed 的现成 0~100 分，不需要再折算。"""
    fg = await fear_greed_service.get_history(redis, start_date=date.today() - timedelta(days=365))
    history = [
        PanicIndexPoint(date=p.date, score=p.score, rating=p.rating, raw_value=None)
        for p in fg.history
    ]
    resp = PanicIndexResponse(
        market="us",
        label=_LABELS["us"],
        current=PanicIndexSnapshot(
            score=fg.current.score, rating=fg.current.rating, date=fg.current.date,
        ),
        previous_week=PanicIndexSnapshot(score=fg.previous_week.score, rating=fg.previous_week.rating),
        previous_month=PanicIndexSnapshot(score=fg.previous_month.score, rating=fg.previous_month.rating),
        history=history,
    )
    await set_panic_index_cache(redis, "us", resp)
    return resp


_BUILDERS = {"us": _build_us, "cn": _build_cn, "hk": _build_hk}


async def get_panic_index(redis: Redis, market: str) -> PanicIndexResponse:
    """检查 Redis 缓存，命中返回缓存，未命中拉取数据源并写缓存。"""
    builder = _BUILDERS.get(market)
    if builder is None:
        raise ValueError(f"unsupported market: {market}")

    cached = await get_panic_index_cache(redis, market)
    if cached is not None:
        logger.info("panic_index_cache_hit", market=market)
        return cached

    logger.info("panic_index_cache_miss", market=market)
    try:
        return await builder(redis)
    except Exception:
        logger.exception("panic_index_fetch_failed", market=market)
        raise
