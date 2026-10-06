"""雷达「好股票」视图：只留当前综合等级达标的股票的买卖点，并给气泡补分析师角标。

产品口径（2026-10-06）：用户要的是「最好的股票里有没有缠论买卖点」，门槛由我们定、不让用户选。
**不写回快照**（和 legacy_view 一样在接口层现算）：快照仍存全部在场信号、不排雷；只有新版 App 带 quality=good 才筛。
门槛用每只股票**当前**的综合等级（不是信号当天的），历史日期的买卖点同样只留当前达标的股票。
分析师角标（美股）= 近 90 天券商净上调 / 下调家数，读 analyst_events 缓存，缺失由后台补。
"""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.signal_radar import RadarDayOut, RadarSignalOut, SignalRadarResponse
from app.services.quant_research import repository
from app.services.quant_research.markets import normalize_symbol
from app.services.quant_research.grading import GRADE_ORDER, cap_grade, grade_for, percentile_of
from app.services.quant_research.scoring import CAP_CEILING, CAP_THRESHOLD
from app.services.signal_radar import analyst_events, fundamental_top
from app.services.signal_radar.quant_filter import QuantGrade

# 「好股票」门槛随股票池大小自适应（2026-10-06）：目标 = 有评级股票的前 GOOD_SHARE，但至少 GOOD_MIN_COUNT 只；
# 从高到低累计各等级只数，到达目标的那一档就是门槛（整档纳入，不在同一档里切——界面才能写「X 及以上」）；
# 门槛不低于 GOOD_FLOOR（小池子 / 整体偏弱的池子不能为了凑数把中下等级算成好股票）。
# 实测（2026-10-06）：纳指 100 → B（16 只）、标普 500 → B、沪深 300 → A-（78 只）、恒生指数 → A-、恒生科技 → B（8 只）。
GOOD_SHARE = 0.25
GOOD_MIN_COUNT = 8
GOOD_FLOOR = "B"
GOOD_CACHE_TTL = 600
ANALYST_WINDOW_DAYS = 90


def choose_cutoff(grades: list[str]) -> str:
    """grades：有评级股票的等级（任意顺序）。返回门槛等级（含）：达标 = 等级不低于它。没有评级时返回 GOOD_FLOOR。"""
    if not grades:
        return GOOD_FLOOR
    target = max(GOOD_MIN_COUNT, math.ceil(GOOD_SHARE * len(grades)))
    floor_idx = GRADE_ORDER.index(GOOD_FLOOR)
    cum = 0
    for idx, grade in enumerate(GRADE_ORDER):
        cum += sum(1 for g in grades if g == grade)
        if cum >= target:
            return GRADE_ORDER[min(idx, floor_idx)]
    return GRADE_ORDER[floor_idx]


QUALITY_GOOD = "good"
QUALITY_GOOD_XM = "good_xm"  # 好股票门槛去掉动量维度（综合分与一票否决都不含动量）
QUALITY_MODES = (QUALITY_GOOD, QUALITY_GOOD_XM)
EXCLUDED_DIM = "momentum"


def rerank_ex_momentum(ranked: list[tuple[str, QuantGrade]]) -> list[tuple[str, QuantGrade]]:
    """去动量口径的重排。

    综合分 = 其余维度分的等权平均，其余维度任一 < CAP_THRESHOLD 则等级封顶 CAP_CEILING；
    等级 = 综合分在**本股票池**有评级股票中的百分位 → 等级（与全样本等级的字母不完全可比，只用来选股和显示）。
    没有分数明细（旧数据）或除动量外无可用维度的股票丢弃；原本就没有综合等级（分析师不足）的也不进。
    """
    scored: list[tuple[str, QuantGrade, float, bool]] = []
    for symbol, g in ranked:
        dims = {k: v for k, v in (g.dim_scores or {}).items() if k != EXCLUDED_DIM}
        if not dims:
            continue
        scored.append((symbol, g, sum(dims.values()) / len(dims), any(v < CAP_THRESHOLD for v in dims.values())))
    dist = sorted(sc for _, _, sc, _ in scored)
    out: list[tuple[str, QuantGrade]] = []
    for symbol, g, sc, vetoed in scored:
        grade = grade_for(percentile_of(sc, dist, lower_better=False))
        if vetoed:
            grade = cap_grade(grade, CAP_CEILING)
        out.append((symbol, replace(g, grade=grade, score=round(sc, 1))))
    return sorted(out, key=lambda t: (GRADE_ORDER.index(t[1].grade or ""), -(t[1].score or 0), t[0]))


async def _with_dim_scores(market: str, ranked: list[tuple[str, QuantGrade]]) -> list[tuple[str, QuantGrade]]:
    """给最新评级补各维度分数（评级历史查询不带）。"""
    stored = {s: normalize_symbol(market, s) for s, _ in ranked}
    scores = await repository.get_dimension_scores(market, [(stored[s], g.as_of) for s, g in ranked])
    return [(s, replace(g, dim_scores=scores.get((stored[s], g.as_of)))) for s, g in ranked]


def _key(market: str, universe: str, mode: str = QUALITY_GOOD) -> str:
    base = f"signal_radar:good:v1:{market}:{universe}"
    return base if mode == QUALITY_GOOD else f"{base}:{mode}"


async def good_stocks(
    market: str, universe: str, redis: Redis, now: datetime, mode: str = QUALITY_GOOD,
) -> tuple[dict[str, dict], int, str] | None:
    """({雷达代码: {grade, score, as_of}}（只含达标的）, 有评级的总只数, 门槛等级)；读取失败返回 None。Redis 缓存 10 分钟。"""
    key = _key(market, universe, mode)
    try:
        cached = await get_json(redis, key)
        if cached and isinstance(cached.get("good"), dict):
            return cached["good"], int(cached.get("rated", 0)), str(cached.get("cutoff") or GOOD_FLOOR)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_good_cache_read_failed", error=str(e))
    loaded = await fundamental_top.load_ranked(market, universe, redis, now.date())
    if loaded is None:
        return None
    ranked, _ = loaded
    if mode == QUALITY_GOOD_XM:
        try:
            ranked = rerank_ex_momentum(await _with_dim_scores(market, ranked))
        except Exception:
            logger.exception("signal_radar_dim_scores_failed", market=market)
            return None
    cutoff = choose_cutoff([g.grade for _, g in ranked if g.grade])
    ok = GRADE_ORDER[:GRADE_ORDER.index(cutoff) + 1]
    good = {s: {"grade": g.grade, "score": g.score, "as_of": g.as_of.isoformat()}
            for s, g in ranked if g.grade in ok}
    try:
        await set_json(redis, key, {"good": good, "rated": len(ranked), "cutoff": cutoff}, expire=GOOD_CACHE_TTL)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_good_cache_write_failed", error=str(e))
    return good, len(ranked), cutoff


def filter_day(day: RadarDayOut, good: dict[str, dict], marks: dict[str, tuple[int, int]]) -> RadarDayOut:
    """一天里只留达标股票的信号；评级换成当前等级；补角标；买卖点数与行业计数按留下的重算。"""
    def keep(signals: list[RadarSignalOut]) -> list[RadarSignalOut]:
        out = []
        for s in signals:
            info = good.get(s.symbol)
            if info is None:
                continue
            up, down = marks.get(s.symbol, (None, None))
            out.append(s.model_copy(update={
                "quant_grade": info["grade"], "quant_score": info["score"], "quant_as_of": info["as_of"],
                "quant_status": "eligible", "analyst_up": up, "analyst_down": down}))
        return out

    signals = keep(day.signals)
    counts: dict[str, dict[str, int]] = {}
    for s in signals:
        if s.sector:
            counts.setdefault(s.sector, {"buy": 0, "sell": 0})[s.side] += 1
    return day.model_copy(update={
        "signals": signals, "candidates": keep(day.candidates), "quant_filter": None,
        "buy_count": sum(s.side == "buy" for s in signals), "sell_count": sum(s.side == "sell" for s in signals),
        "sector_counts": counts})


async def apply_quality(
    resp: SignalRadarResponse, redis: Redis, *, now: datetime | None = None, mode: str = QUALITY_GOOD,
) -> SignalRadarResponse:
    """只留达标股票的买卖点（门槛自适应，见 choose_cutoff）。评级读取失败时原样返回（不能因为评级挂了让雷达变空）。"""
    now = now or datetime.now(UTC)
    if not resp.universe or not resp.days:
        return resp
    loaded = await good_stocks(resp.market, resp.universe, redis, now, mode)
    if loaded is None:
        return resp
    good, rated, cutoff = loaded
    marks: dict[str, tuple[int, int]] = {}
    pending = 0
    if resp.market in analyst_events.SUPPORTED_MARKETS:
        symbols = sorted({s.symbol for d in resp.days for s in d.signals if s.symbol in good})
        if symbols:
            cached = await analyst_events.cached_with_refresh(resp.market, resp.universe + ":quality", symbols, redis, now)
            since = now.date() - timedelta(days=ANALYST_WINDOW_DAYS)
            marks = {s: analyst_events.net_counts(cached[s]["actions"], since) for s in symbols if s in cached}
            pending = sum(1 for s in symbols if s not in cached)
    return resp.model_copy(update={
        "days": [filter_day(d, good, marks) for d in resp.days],
        "quality": mode, "quality_threshold": cutoff, "quality_good_count": len(good),
        "quality_rated_count": rated, "analyst_pending": pending})
