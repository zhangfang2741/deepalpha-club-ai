"""信号雷达服务：扫描科技 ETF 成分股跑缠论，按日重建「市场买卖点全景」。

分层：
- 纯聚合函数（signal_strength / build_signal_history / build_days）无 IO，单测覆盖；
- compute_market 负责编排（并发拉行情 + 缠论 + Redis 缓存）。

按日重建口径（核心，别写回「只存最新一条」的旧模型）：
每只股票在缠论分析里可能有一串历史买卖点（result.signals），不是只有一条。
过去的实现只取每只股票的「最新一条」信号按其诞生日期分桶，越往前翻的日子能配
上「诞生日恰好是那天」的股票越少，越翻越稀疏——那根本不是「某天全市场快照」，
只是「各股票最新信号的日期分布尾巴」。
现在改成：先拿到每只股票的完整信号历史，再对每一个要展示的交易日 D，取每只
股票「D 当天或之前最近一条」信号作为它在 D 这天的「在场」信号，直到被更新的
信号覆盖为止。这样任意展示日期都能看到当时全市场有效的买卖点全景。

强度口径：形态技术面强度统一使用信号自带的 strong/medium/weak 标签折算
（signal_strength），不用 recommendation.score——score 是分析当下对整条序列
算出的即时加权净值，对着几周前的历史信号回填没有意义，会导致同一个信号在
被翻看的不同日子里强度/大小忽大忽小。方向由买卖点决定（buy=红 / sell=绿）。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.signal_radar import RadarDayOut, RadarSignalOut, SignalRadarResponse
from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.signal_radar.constituents import resolve_constituents
from app.services.signal_radar.universe import get_universe
from app.services.skills.kline import fetch_kline

_analyzer = ChanAnalyzer()

# 缠论窗口锚定所需的 warmup 天数（与 chan.py 的日线口径一致）
_WARMUP_DAYS = 180
# 并发扫描的信号量：控制对行情源的压力
_SCAN_CONCURRENCY = 8

# 买卖点自身强弱标签 → 形态技术面强度（0~1）。见模块 docstring：不用 score 是
# 因为要跨很多天复用同一把尺子，只有信号自己在诞生时就确定的标签才不会变。
_SIGNAL_STRENGTH = {"strong": 0.8, "medium": 0.55, "weak": 0.35}

_CACHE_PREFIX = "signal_radar"
_CACHE_TTL = 3600 * 6  # 6h


@dataclass
class RawSignal:
    """单只股票的一条买卖点（聚合前的中间结构）。"""

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


def signal_strength(label: str) -> float:
    """买卖点自身强弱标签（strong/medium/weak）→ 形态技术面强度（0~1）。"""
    return _SIGNAL_STRENGTH.get(label, 0.5)


def build_signal_history(symbol: str, name: str, result: ChanAnalysisResult) -> list[RawSignal]:
    """从一只股票的缠论结果里取出全部买卖点历史。

    不只是最新一条，按日期升序返回，供按日重建市场快照时找「某天为止最近一条」用。
    没有买卖点返回空列表。
    """
    history = [
        RawSignal(
            symbol=symbol,
            name=name,
            side="buy" if sig.is_buy else "sell",
            label=sig.label,
            signal_type=sig.type,
            date=sig.time[:10],
            price=round(sig.price, 2),
            strength=signal_strength(sig.strength),
            bias="bullish" if sig.is_buy else "bearish",
            signal_strength=sig.strength,
            confirmed=sig.confirmed,
        )
        for sig in result.signals
    ]
    history.sort(key=lambda r: r.date)
    return history


def build_days(
    histories: list[list[RawSignal]], trading_days: list[str], *, top_n: int,
) -> list[RadarDayOut]:
    """按 trading_days（最新在前）逐日重建市场快照。

    histories 是「每只股票的信号历史」的列表（每条已按日期升序）。对每个展示日
    D，每只股票取它历史里日期 <= D 的最后一条作为「D 当天在场」的信号；股票数量
    很小（几十到上百），这里用线性扫描换清晰，不做二分。
    """
    out: list[RadarDayOut] = []
    for day in trading_days:
        active: list[RawSignal] = []
        for history in histories:
            candidate: RawSignal | None = None
            for r in history:
                if r.date > day:
                    break
                candidate = r
            if candidate is not None:
                active.append(candidate)

        items = sorted(active, key=lambda r: r.strength, reverse=True)[:top_n]
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


def _trading_days_from_bars(bars: list[dict], *, cutoff: str, end_date: str, limit: int) -> list[str]:
    """从一串日线 bar 里提取 [cutoff, end_date] 内的交易日期，最新在前，最多取 limit 个。"""
    dates = sorted({b["time"][:10] for b in bars if cutoff <= b["time"][:10] <= end_date}, reverse=True)
    return dates[:limit]


def _fallback_trading_days(*, end_date: str, limit: int) -> list[str]:
    """拿不到任何 K 线时的兜底。

    按自然日往前数、跳过周六周日（不识别节假日，只在行情源整体不可用时才会
    走到这里，凑合出个大致的交易日序列）。
    """
    out: list[str] = []
    d = date.fromisoformat(end_date)
    while len(out) < limit:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out


async def _scan_symbol(
    symbol: str, name: str, *, user_id: int | None, start_date: str, end_date: str,
    redis: Redis,
) -> list[RawSignal]:
    """扫描单只股票：拉日线 → 缠论 → 取全部买卖点历史。"""
    try:
        bars = await fetch_kline(
            user_id=user_id, symbol=symbol, start_date=start_date,
            end_date=end_date, freq="daily", redis=redis,
        )
    except Exception as e:  # noqa: BLE001 单只失败不影响整体扫描
        logger.warning("signal_radar_kline_failed", symbol=symbol, error=str(e))
        return []

    if not bars:
        return []

    try:
        result = _analyzer.analyze(symbol, bars, lang="zh")
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_analyze_failed", symbol=symbol, error=str(e))
        return []

    return build_signal_history(symbol, name, result)


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
    days: int = 30, window: int = 45, top_n: int = 10,
) -> SignalRadarResponse:
    """全量扫描一个市场并按日重建市场快照（不读缓存，计算完写入缓存）。"""
    universe = get_universe(market)
    if universe is None:
        raise ValueError(f"unsupported market: {market}")

    # 成分股：优先 FMP ETF 持仓动态刷新，取不到回退 curated 静态清单。
    constituents = await resolve_constituents(market, redis=redis)

    today = date.today()
    end_date = today.isoformat()
    # 取足够 warmup + 候选窗口的历史；缠论在完整序列上算以消除左边界漂移。
    start_date = (today - timedelta(days=_WARMUP_DAYS + window * 2)).isoformat()
    cutoff = (today - timedelta(days=window)).isoformat()

    sem = asyncio.Semaphore(_SCAN_CONCURRENCY)

    async def _one(symbol: str, name: str) -> list[RawSignal]:
        async with sem:
            return await _scan_symbol(
                symbol, name, user_id=user_id, start_date=start_date,
                end_date=end_date, redis=redis,
            )

    histories = await asyncio.gather(*[_one(sym, name) for sym, name in constituents])
    histories = [h for h in histories if h]

    # 展示的交易日历：用 ETF 自身的日线拿真实交易日（含具体哪几天开市），
    # 拿不到就退化成「跳过周末」的近似日历。
    try:
        etf_bars = await fetch_kline(
            user_id=user_id, symbol=universe.etf_symbol, start_date=cutoff,
            end_date=end_date, freq="daily", redis=redis,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_etf_kline_failed", market=market, error=str(e))
        etf_bars = []
    trading_days = (
        _trading_days_from_bars(etf_bars, cutoff=cutoff, end_date=end_date, limit=days)
        if etf_bars else _fallback_trading_days(end_date=end_date, limit=days)
    )

    resp = SignalRadarResponse(
        market=market,
        etf_name=universe.etf_name,
        universe_size=len(constituents),
        as_of=end_date,
        top_n=top_n,
        days=build_days(histories, trading_days, top_n=top_n),
        status="ready",
    )
    logger.info(
        "signal_radar_computed", market=market,
        universe=len(universe.constituents), symbols_with_signals=len(histories),
        days=len(resp.days),
    )
    await _write_cache(redis, resp)
    return resp


async def peek_cache(redis: Redis, market: str) -> SignalRadarResponse | None:
    """只读缓存（不触发扫描），供 API 的 generating 轮询模式使用。"""
    return await _read_cache(redis, market)


async def get_market(
    market: str, *, redis: Redis, user_id: int | None = None,
    days: int = 30, window: int = 45, top_n: int = 10, force: bool = False,
) -> SignalRadarResponse:
    """读缓存优先；未命中则同步扫描（首访较慢，命中后走缓存）。"""
    if not force:
        cached = await _read_cache(redis, market)
        if cached is not None:
            return cached
    return await compute_market(
        market, redis=redis, user_id=user_id, days=days, window=window, top_n=top_n,
    )
