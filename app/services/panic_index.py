"""三地恐慌指数服务：统一美股 VIX / A股上证指数 / 港股恒生指数为同一套 0~100 分数。

数据源：
- us：复用现有 app.services.fear_greed（CNN Fear & Greed，已经是 0~100 分，直接搬字段）。
- cn：akshare `stock_zh_index_daily`（上证指数，新浪源）。
- hk：akshare `stock_hk_index_daily_sina`（恒生指数，新浪源，跟 cn 同一套算法）。

折算规则：cn/hk 直接对指数收盘价算 RSI(14)（Wilder 平滑，与
app/services/industry_panic 的行业 ETF 情绪同一套算法，见 app/services/rsi.py），
`score = RSI` 直接当分数用——RSI 天然就是 0~100，越高越强势=越贪婪，越低越弱势=越
恐慌，不需要再套一层百分位转换。这样可以直接复用 CNN 的 Extreme Fear/Fear/
Neutral/Greed/Extreme Greed 五档阈值。

（曾经用波动率百分位数——A股 50ETF-QVIX / 港股 VHSI 相对自身近一年分位数折算——
但那套算法只反映"贵不贵"一个维度，跟 CNN 官方 7 因子合成的美股版本不是同一把尺子，
换成指数动能 RSI 更直观、也跟项目里已有的行业恐慌页面用同一套算法。）
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
from app.services.rsi import rsi_series

# 一周 / 一月对应的交易日回溯步数，与 previous_week/previous_month 语义对齐。
_WEEK_LAG = 5
_MONTH_LAG = 21
_RSI_PERIOD = 14

_LABELS = {
    "us": "VIX 恐慌贪婪指数",
    "cn": "A股情绪 (上证指数 RSI)",
    "hk": "港股情绪 (恒生指数 RSI)",
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
    close: float


def _snapshot_at(points: list[PanicIndexPoint], lag: int) -> PanicIndexSnapshot:
    """取倒数第 lag+1 个点做「N 天前」快照；序列不够长时退回最早的点。"""
    idx = max(0, len(points) - 1 - lag)
    p = points[idx] if points else None
    if p is None:
        return PanicIndexSnapshot(score=50.0, rating="Neutral")
    return PanicIndexSnapshot(score=p.score, rating=p.rating, raw_value=p.raw_value)


def _price_to_points(raw: list[_RawPoint]) -> list[PanicIndexPoint]:
    """把一串指数收盘价转换成 0~100 恐慌贪婪分数序列（RSI 越高越贪婪）。

    前 _RSI_PERIOD 个点没有 RSI（预热期），直接丢弃不进历史序列。
    """
    closes = [p.close for p in raw]
    rsi_vals = rsi_series(closes, period=_RSI_PERIOD)
    points: list[PanicIndexPoint] = []
    for p, rsi in zip(raw, rsi_vals, strict=False):
        if rsi is None:
            continue
        score = round(rsi, 1)
        points.append(PanicIndexPoint(
            date=p.date, score=score, rating=_score_to_rating(score), raw_value=p.close,
        ))
    return points


def _fetch_cn_index() -> pd.DataFrame:
    return ak.stock_zh_index_daily(symbol="sh000001")


def _fetch_hk_index() -> pd.DataFrame:
    return ak.stock_hk_index_daily_sina(symbol="HSI")


async def _build_cn(redis: Redis) -> PanicIndexResponse:
    df = await asyncio.to_thread(_fetch_cn_index)
    return await _build_from_price_df(redis, market="cn", df=df)


async def _build_hk(redis: Redis) -> PanicIndexResponse:
    df = await asyncio.to_thread(_fetch_hk_index)
    return await _build_from_price_df(redis, market="hk", df=df)


async def _build_from_price_df(redis: Redis, *, market: str, df: pd.DataFrame) -> PanicIndexResponse:
    raw = sorted(
        (
            _RawPoint(date=str(r["date"])[:10], close=float(r["close"]))
            for _, r in df.dropna(subset=["close"]).iterrows()
            if float(r["close"]) > 0
        ),
        key=lambda p: p.date,
    )
    points = _price_to_points(raw)

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
