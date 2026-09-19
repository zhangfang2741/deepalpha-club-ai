"""信号雷达服务：扫描科技 ETF 成分股跑缠论，聚合每日买卖点前 N 只。

分层：
- 纯聚合函数（strength_from_score / aggregate_days）无 IO，单测覆盖；
- scan_market 负责编排（并发拉行情 + 缠论 + Redis 缓存）。

强度口径：气泡的「大小」与「颜色深浅」统一由**形态技术面强度**驱动，
即缠论多因子加权净值 recommendation.score 的绝对值归一化到 0~1
（见 app/services/chan/bias.py，STRONG_BIAS_THRESHOLD=3.5）。方向由买卖点决定
（buy=红 / sell=绿），与详情页 bias.py 的加权口径一致。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.signal_radar import RadarDayOut, RadarSignalOut, SignalRadarResponse
from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.signal_radar.universe import get_universe
from app.services.skills.kline import fetch_kline

_analyzer = ChanAnalyzer()

# 缠论窗口锚定所需的 warmup 天数（与 chan.py 的日线口径一致）
_WARMUP_DAYS = 180
# 并发扫描的信号量：控制对行情源的压力
_SCAN_CONCURRENCY = 8

# score 绝对值 → 强度归一化的除数。score 由多因子加权而来，
# 单方向叠满约 4~6 分，取 5.0 使「偏强（≈3.5）」落在 0.7 附近、饱和于 1.0。
_STRENGTH_SCALE = 5.0
# 无 recommendation（结构不足）时，按买卖点自身强度兜底一个形态强度
_SIGNAL_STRENGTH_FALLBACK = {"strong": 0.8, "medium": 0.55, "weak": 0.35}

_CACHE_PREFIX = "signal_radar"
_CACHE_TTL = 3600 * 6  # 6h


@dataclass
class RawSignal:
    """单只股票的当日买卖点（聚合前的中间结构）。"""

    symbol: str
    name: str
    side: str            # buy / sell
    label: str
    signal_type: str
    date: str
    price: float
    strength: float      # 形态技术面强度 0~1
    bias: str
    signal_strength: str
    confirmed: bool


def strength_from_score(score: float) -> float:
    """缠论加权净值 → 形态技术面强度（0~1）。"""
    return round(min(1.0, abs(score) / _STRENGTH_SCALE), 3)


def build_raw_signal(symbol: str, name: str, result: ChanAnalysisResult) -> RawSignal | None:
    """从一只股票的缠论结果里取「最新买卖点」，折算成一条 RawSignal。

    无买卖点则返回 None。形态技术面强度优先取 recommendation.score，
    结构不足（无 recommendation）时按买卖点自身强度兜底。
    """
    sig = result.latest_signal or (result.signals[-1] if result.signals else None)
    if sig is None:
        return None

    if result.recommendation is not None:
        strength = strength_from_score(result.recommendation.score)
        bias = result.recommendation.bias
    else:
        strength = _SIGNAL_STRENGTH_FALLBACK.get(sig.strength, 0.5)
        bias = "bullish" if sig.is_buy else "bearish"

    return RawSignal(
        symbol=symbol,
        name=name,
        side="buy" if sig.is_buy else "sell",
        label=sig.label,
        signal_type=sig.type,
        date=sig.time[:10],
        price=round(sig.price, 2),
        strength=strength,
        bias=bias,
        signal_strength=sig.strength,
        confirmed=sig.confirmed,
    )


def aggregate_days(raw: list[RawSignal], *, days: int, top_n: int) -> list[RadarDayOut]:
    """把 RawSignal 按日期分桶，每日按强度降序取前 top_n，返回最近 days 个交易日（最新在前）。"""
    buckets: dict[str, list[RawSignal]] = {}
    for r in raw:
        buckets.setdefault(r.date, []).append(r)

    out: list[RadarDayOut] = []
    for day in sorted(buckets.keys(), reverse=True)[:days]:
        items = sorted(buckets[day], key=lambda r: r.strength, reverse=True)[:top_n]
        out.append(RadarDayOut(
            date=day,
            buy_count=sum(1 for r in items if r.side == "buy"),
            sell_count=sum(1 for r in items if r.side == "sell"),
            signals=[
                RadarSignalOut(
                    symbol=r.symbol, name=r.name, side=r.side, label=r.label,
                    signal_type=r.signal_type, date=r.date, price=r.price,
                    strength=r.strength, bias=r.bias,
                    signal_strength=r.signal_strength, confirmed=r.confirmed,
                )
                for r in items
            ],
        ))
    return out


async def _scan_symbol(
    symbol: str, name: str, *, user_id: int | None, start_date: str, end_date: str,
    redis: Redis, cutoff: str,
) -> RawSignal | None:
    """扫描单只股票：拉日线 → 缠论 → 取最新买卖点（须落在 cutoff 之后）。"""
    try:
        bars = await fetch_kline(
            user_id=user_id, symbol=symbol, start_date=start_date,
            end_date=end_date, freq="daily", redis=redis,
        )
    except Exception as e:  # noqa: BLE001 单只失败不影响整体扫描
        logger.warning("signal_radar_kline_failed", symbol=symbol, error=str(e))
        return None

    if not bars:
        return None

    try:
        result = _analyzer.analyze(symbol, bars, lang="zh")
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_analyze_failed", symbol=symbol, error=str(e))
        return None

    raw = build_raw_signal(symbol, name, result)
    if raw is None or raw.date < cutoff:
        return None
    return raw


def _cache_key(market: str) -> str:
    return f"{_CACHE_PREFIX}:{market}"


async def _read_cache(redis: Redis, market: str) -> SignalRadarResponse | None:
    try:
        rawval = await redis.get(_cache_key(market))
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cache_read_error", market=market, error=str(e))
        return None
    if rawval is None:
        return None
    try:
        return SignalRadarResponse.model_validate_json(rawval)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cache_deserialize_error", market=market, error=str(e))
        return None


async def _write_cache(redis: Redis, data: SignalRadarResponse) -> None:
    try:
        await redis.set(_cache_key(data.market), data.model_dump_json(), ex=_CACHE_TTL)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cache_write_error", market=data.market, error=str(e))


async def compute_market(
    market: str, *, redis: Redis, user_id: int | None = None,
    days: int = 8, window: int = 30, top_n: int = 10,
) -> SignalRadarResponse:
    """全量扫描一个市场并聚合结果（不读缓存，计算完写入缓存）。"""
    universe = get_universe(market)
    if universe is None:
        raise ValueError(f"unsupported market: {market}")

    today = date.today()
    end_date = today.isoformat()
    # 取足够 warmup + 候选窗口的历史；缠论在完整序列上算以消除左边界漂移。
    start_date = (today - timedelta(days=_WARMUP_DAYS + window * 2)).isoformat()
    cutoff = (today - timedelta(days=window)).isoformat()

    sem = asyncio.Semaphore(_SCAN_CONCURRENCY)

    async def _one(symbol: str, name: str) -> RawSignal | None:
        async with sem:
            return await _scan_symbol(
                symbol, name, user_id=user_id, start_date=start_date,
                end_date=end_date, redis=redis, cutoff=cutoff,
            )

    results = await asyncio.gather(
        *[_one(sym, name) for sym, name in universe.constituents]
    )
    raw = [r for r in results if r is not None]

    resp = SignalRadarResponse(
        market=market,
        etf_name=universe.etf_name,
        universe_size=len(universe.constituents),
        as_of=end_date,
        top_n=top_n,
        days=aggregate_days(raw, days=days, top_n=top_n),
        status="ready",
    )
    logger.info(
        "signal_radar_computed", market=market,
        universe=len(universe.constituents), signals=len(raw), days=len(resp.days),
    )
    await _write_cache(redis, resp)
    return resp


async def peek_cache(redis: Redis, market: str) -> SignalRadarResponse | None:
    """只读缓存（不触发扫描），供 API 的 generating 轮询模式使用。"""
    return await _read_cache(redis, market)


async def get_market(
    market: str, *, redis: Redis, user_id: int | None = None,
    days: int = 8, window: int = 30, top_n: int = 10, force: bool = False,
) -> SignalRadarResponse:
    """读缓存优先；未命中则同步扫描（首访较慢，命中后走缓存）。"""
    if not force:
        cached = await _read_cache(redis, market)
        if cached is not None:
            return cached
    return await compute_market(
        market, redis=redis, user_id=user_id, days=days, window=window, top_n=top_n,
    )
