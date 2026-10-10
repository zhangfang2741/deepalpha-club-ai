"""基本面动向雷达：从最近一天批量结果里的动向事实（trend.py）挑出「最近在变好」的公司，按时间放进三圈。

- 预期上调（estimates）：本财年 EPS 一致预期近 7 天涨 ≥ 2% 放最内圈，否则近 30 天 ≥ 5% 放中圈，否则近 90 天 ≥ 10% 放外圈；
  覆盖分析师 ≥ 3 位才算（人太少一致预期会被一两位分析师带着跳）。
- 评级改善（rating，2026-10-10 起 App 用它代替下面的质地改善）：我们自己的综合等级，在**同一评级方法下**比窗口（7 / 30 / 90 天）里最早一个评级日至少
  升 1 档；按最小的那个窗口放圈。方法升级前后不是同一把尺子，不比较；刚升级时历史是空的，这一类会先空着、攒几天才有。
- 质地改善（quality，旧版 App 还在用）：最近一季披露在 90 天内，经营利润率或自由现金流利润率比上一季高 ≥ 1 个百分点，
  四项（营收同比 / 毛利率 / 经营利润率 / 自由现金流利润率）里至少两项变好，且没有一项变差超过 3 个百分点；按披露距今放圈（7 / 30 / 90 天）。
只陈列事实（谁在什么方面变好了、变了多少），不排名次、不是推荐；门槛随响应返回，App 推导说明直接用。

「高价值」筛选（2026-10-10）：每个条目带 `good`——综合等级达到本市场的「好股票」门槛（与信号雷达同一套自适应规则
`signal_radar.quality_view.choose_cutoff`：有评级股票的前 25%、至少 8 只、不低于 B，整档纳入）；App 默认只画 good 的，
也可以切到「全部」。条目另带 `magnitude`（变化是入圈门槛的几倍，跨圈可比）与 `sector`（雷达行业 key）。
"""

from __future__ import annotations

import asyncio
import time

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.quant_research import RatingChangeOut, TrendFacts, TrendRadarItem, TrendRadarOut
from app.services.quant_research import repository as repo
from app.services.quant_research.batch import latest_key
from app.services.quant_research.builder import METHODOLOGY_VERSION
from app.services.quant_research.copy import Lang
from app.services.quant_research.grading import GRADE_ORDER
from app.services.signal_radar.quality_view import choose_cutoff
from app.services.signal_radar.sectors import load_sector_tags, lookup_tag

RINGS = (7, 30, 90)
EPS_UP = {7: 0.02, 30: 0.05, 90: 0.10}
MIN_ANALYSTS = 3
QUALITY_MARGIN_PP = 1.0        # 经营利润率或自由现金流利润率至少提高这么多
QUALITY_IMPROVED_MIN = 2       # 四项里至少这么多项变好
QUALITY_WORST_PP = -3.0        # 任何一项变差不能超过这么多
QUALITY_EPS = 0.1              # 变化小于 0.1 个百分点视为没变
RATING_MIN_STEPS = 1           # 综合等级至少升这么多档才算评级改善
RATING_BULK_RATIO = 0.3        # 池子里有评级的股票超过这个比例同时升档，视为方法论升级 / 全员重评，一条都不要
PER_KIND_LIMIT = 60
CACHE_TTL = 6 * 3600


def estimates_item(f: TrendFacts, *, down: bool = False) -> tuple[int, float] | None:
    """(圈, 变化幅度)；不满足任何一圈返回 None。down=True 看下调：变化率 ≤ -门槛，幅度取绝对值。"""
    if f.n_analysts < MIN_ANALYSTS:
        return None
    for days, chg in ((7, f.eps_rev_7d), (30, f.eps_rev_30d), (90, f.eps_rev_90d)):
        if chg is None:
            continue
        if (down and chg <= -EPS_UP[days]) or (not down and chg >= EPS_UP[days]):
            return days, abs(chg)
    return None


def quality_item(f: TrendFacts, as_of: date) -> tuple[int, float] | None:
    """(圈, 改善的百分点合计)；不满足返回 None。"""
    if not f.filing_date:
        return None
    try:
        age = (as_of - date.fromisoformat(f.filing_date[:10])).days
    except ValueError:
        return None
    if age < 0 or age > RINGS[-1]:
        return None
    deltas = [d for d in (f.d_rev_yoy_pp, f.d_gross_m_pp, f.d_ebit_m_pp, f.d_fcf_m_pp) if d is not None]
    margin_up = any(d is not None and d >= QUALITY_MARGIN_PP for d in (f.d_ebit_m_pp, f.d_fcf_m_pp))
    improved = sum(d > QUALITY_EPS for d in deltas)
    if not margin_up or improved < QUALITY_IMPROVED_MIN or any(d < QUALITY_WORST_PP for d in deltas):
        return None
    ring = next(r for r in RINGS if age <= r)
    return ring, round(sum(d for d in deltas if d > 0), 2)


def _magnitude(kind: str, ring: int, strength: float) -> float:
    """变化是入圈门槛的几倍：预期 = 变化率 ÷ 该圈门槛，质地 = 改善百分点 ÷ 利润率门槛（kind 只认 estimates / quality）。"""
    unit = EPS_UP[ring] if kind == "estimates" else QUALITY_MARGIN_PP
    return round(strength / unit, 2)


def _select(items: list[TrendRadarItem]) -> list[TrendRadarItem]:
    """达标的与其余的各取 PER_KIND_LIMIT 个（互不挤占，达标的不会被一堆不达标的顶掉），仍按圈、幅度排。"""
    good = [i for i in items if i.good][:PER_KIND_LIMIT]
    rest = [i for i in items if not i.good][:PER_KIND_LIMIT]
    return sorted(good + rest, key=lambda i: (i.ring_days, -i.strength))


@dataclass
class GradePoint:
    """某只股票某个评级日的综合等级。"""
    as_of: date
    grade: str | None
    score: float | None
    version: str | None


def rating_item(points: list[GradePoint], *, down: bool = False) -> RatingChangeOut | None:
    """综合等级是否在最近 7 / 30 / 90 天里升档（down=True 看降档）；返回落在哪一圈。不满足返回 None。

    只和同一评级方法（methodology_version）下的历史比：两边都有版本且不同就不比较（方法升级当天会有一大批假升降）。
    对比的是窗口内**最早**一个评级日（「N 天前 vs 现在」），按最小的窗口放圈。steps 总是正数（升 / 降了几档）。
    """
    seq = sorted((p for p in points if p.grade in GRADE_ORDER), key=lambda p: p.as_of)
    if len(seq) < 2:
        return None
    cur = seq[-1]
    same = [p for p in seq[:-1] if not (p.version and cur.version and p.version != cur.version)]
    cur_rank = GRADE_ORDER.index(cur.grade or "")
    for ring in RINGS:
        window = [p for p in same if p.as_of >= cur.as_of - timedelta(days=ring)]
        if not window:
            continue
        ref = window[0]
        ref_rank = GRADE_ORDER.index(ref.grade or "")
        steps = (cur_rank - ref_rank) if down else (ref_rank - cur_rank)   # GRADE_ORDER 下标越小等级越高
        if steps >= RATING_MIN_STEPS:
            delta = round(cur.score - ref.score, 1) if cur.score is not None and ref.score is not None else None
            return RatingChangeOut(from_grade=ref.grade or "", to_grade=cur.grade or "", steps=steps, score_delta=delta,
                                   from_date=ref.as_of.isoformat(), to_date=cur.as_of.isoformat(), ring_days=ring)
    return None


def rating_changes(history: dict[str, list[GradePoint]], *, down: bool = False) -> dict[str, RatingChangeOut]:
    """{代码: 评级序列} → {代码: 评级改善 / 评级下降}。池子里超过 RATING_BULK_RATIO 的有评级股票同时变档视为全员重评，返回空。"""
    out = {s: r for s, pts in history.items() if (r := rating_item(pts, down=down)) is not None}
    rated = sum(1 for pts in history.values() if any(p.grade in GRADE_ORDER for p in pts))
    if rated and len(out) / rated > RATING_BULK_RATIO:
        logger.info("quant_trend_rating_bulk_skipped", changed=len(out), rated=rated, down=down)
        return {}
    return out


def _rating_magnitude(rc: RatingChangeOut) -> float:
    """升 / 降的档数为主、综合分变化的绝对值只作同档数里的先后（零头不超过 0.99）。"""
    return round(rc.steps + min(abs(rc.score_delta or 0.0), 99.0) / 100, 2)


def build_trend_radar(rows: list[dict], *, market: str, as_of: date | None,
                      tags: dict[str, str] | None = None,
                      ratings: Mapping[str, RatingChangeOut | None] | None = None,
                      ratings_down: Mapping[str, RatingChangeOut | None] | None = None) -> TrendRadarOut:
    """把每只股票的动向事实、评级变化整理成雷达条目。

    rows：{symbol, name, grade, sector_name, trend(dict)}；tags：代码 → 雷达行业 key（可缺）；
    ratings / ratings_down：代码 → 评级改善 / 评级下降（可缺）。

    上调一侧（预期上调、质地改善、评级改善）在 App 里画红色，下调一侧（预期下调、评级下降）画绿色——和缠论雷达的红买绿卖同一套颜色。
    下调一侧的「精选」：评级下降的股票现在可能已经掉出门槛，原来达标也算（否则最值得看的恰好被筛掉）。
    """
    rated = [r["grade"] for r in rows if r.get("grade") in GRADE_ORDER]
    cutoff = choose_cutoff(rated) if rated else None
    cutoff_rank = GRADE_ORDER.index(cutoff) if cutoff else None

    def qualifies(grade: str | None) -> bool:
        return cutoff_rank is not None and grade in GRADE_ORDER and GRADE_ORDER.index(grade or "") <= cutoff_rank

    buckets: dict[str, list[TrendRadarItem]] = {k: [] for k in
                                                ("estimates", "estimates_down", "quality", "rating", "rating_down")}
    for r in rows:
        grade = r.get("grade")
        base = {
            "symbol": r["symbol"], "name": r.get("name"), "sector_name": r.get("sector_name"), "grade": grade,
            "good": qualifies(grade),
            "sector": lookup_tag(tags, r["symbol"]) if tags else None,
        }
        f = TrendFacts(**r["trend"]) if r.get("trend") else None
        if f is not None:
            if (e := estimates_item(f)) is not None:
                buckets["estimates"].append(TrendRadarItem(
                    **base, kind="estimates", ring_days=e[0], strength=round(e[1], 4),
                    magnitude=_magnitude("estimates", e[0], e[1]), facts=f))
            if (e := estimates_item(f, down=True)) is not None:
                buckets["estimates_down"].append(TrendRadarItem(
                    **base, kind="estimates_down", ring_days=e[0], strength=round(e[1], 4),
                    magnitude=_magnitude("estimates", e[0], e[1]), facts=f))
            if as_of is not None and (q := quality_item(f, as_of)) is not None:
                buckets["quality"].append(TrendRadarItem(
                    **base, kind="quality", ring_days=q[0], strength=q[1],
                    magnitude=_magnitude("quality", q[0], q[1]), facts=f))
        if (rc := (ratings or {}).get(r["symbol"])) is not None:
            mag = _rating_magnitude(rc)
            buckets["rating"].append(TrendRadarItem(**base, kind="rating", ring_days=rc.ring_days, strength=mag,
                                                    magnitude=mag, rating=rc, facts=f or TrendFacts()))
        if (rd := (ratings_down or {}).get(r["symbol"])) is not None:
            mag = _rating_magnitude(rd)
            item = TrendRadarItem(**{**base, "good": qualifies(grade) or qualifies(rd.from_grade)},
                                  kind="rating_down", ring_days=rd.ring_days, strength=mag, magnitude=mag,
                                  rating=rd, facts=f or TrendFacts())
            buckets["rating_down"].append(item)
    for lst in buckets.values():
        lst.sort(key=lambda i: (i.ring_days, -i.strength))
    picked = {k: _select(v) for k, v in buckets.items()}
    thresholds = {f"eps_up_{d}d": v for d, v in EPS_UP.items()} | {
        "min_analysts": MIN_ANALYSTS, "quality_margin_pp": QUALITY_MARGIN_PP,
        "quality_improved_min": QUALITY_IMPROVED_MIN, "quality_worst_pp": QUALITY_WORST_PP,
        "rating_min_steps": RATING_MIN_STEPS}
    counts: dict[str, int] = {}
    for k, v in picked.items():
        counts[k] = len(v)
        counts[f"{k}_good"] = sum(i.good for i in v)
    return TrendRadarOut(
        market=market, as_of=as_of.isoformat() if as_of else None, rings=list(RINGS),
        thresholds=thresholds, items=[i for v in picked.values() for i in v], good_grade=cutoff, counts=counts)


async def _load_rating_changes(
    market: str, day: date, symbols: set[str],
) -> tuple[dict[str, RatingChangeOut], dict[str, RatingChangeOut]]:
    """池子里每只股票最近 90 天的综合等级序列 → (评级改善, 评级下降)。读取失败只是这两类为空，不影响其它类别。"""
    try:
        rows = await repo.trend_grade_history(market, day - timedelta(days=RINGS[-1] + 5), day)
    except Exception:  # noqa: BLE001
        logger.exception("quant_trend_rating_history_failed", market=market)
        return {}, {}
    history: dict[str, list[GradePoint]] = {}
    for sym, as_of, grade, score, version in rows:
        if sym in symbols:
            history.setdefault(sym, []).append(GradePoint(as_of, grade, score, version))
    return rating_changes(history), rating_changes(history, down=True)


# 全市场的原料（最新一天的动向事实 + 90 天评级历史算出的升降）在进程里缓存：切换指数、自选、中英文都不用再读一遍库
# （评级历史全市场约十几万行，是请求变慢的大头）。同一市场同时来多个请求只算一次（锁），新一天批量后换键。
_INPUT_TTL = 30 * 60
_inputs_cache: dict[tuple[str, str, str | None], tuple[float, tuple]] = {}
_inputs_locks: dict[tuple[str, str], asyncio.Lock] = {}


async def _market_inputs(market: str, lang: str, latest: str | None):
    key = (market, lang, latest)
    now = time.monotonic()
    if (hit := _inputs_cache.get(key)) and now - hit[0] < _INPUT_TTL:
        return hit[1]
    lock = _inputs_locks.setdefault((market, lang), asyncio.Lock())
    async with lock:
        now = time.monotonic()
        if (hit := _inputs_cache.get(key)) and now - hit[0] < _INPUT_TTL:
            return hit[1]
        day, rows = await repo.trend_radar_rows(market, lang, as_of=date.fromisoformat(latest) if latest else None)
        ratings, ratings_down = (
            await _load_rating_changes(market, day, {r["symbol"] for r in rows}) if rows and day else ({}, {}))
        value = (day, rows, ratings, ratings_down)
        if rows and day:
            for k in [k for k in _inputs_cache if k[:2] == (market, lang)]:
                del _inputs_cache[k]
            _inputs_cache[key] = (time.monotonic(), value)
        return value


def filter_rows(rows: list[dict], members: set[str] | None) -> list[dict]:
    """只留股票池里的公司；members 为 None 表示不限（全市场），空集合表示池子是空的。"""
    return rows if members is None else [r for r in rows if r["symbol"] in members]


def _cache_key(market: str, as_of: str, lang: str, scope: str = "all") -> str:
    return f"quant:{market}:trend_radar:v5:{METHODOLOGY_VERSION}:{scope}:{as_of}:{lang}"


async def get_trend_radar(market: str, lang: Lang, *, redis: Redis | None, members: set[str] | None = None,
                          scope: str = "all", cacheable: bool = True) -> TrendRadarOut:
    """最近一天的动向雷达；整份结果按（方法版本, 股票池, 批量日期, 语言）缓存 6 小时，新一天批量后自动换键。

    members / scope：只看某个指数（或自选）的成分股，和信号雷达选的指数一致；「好股票」门槛也按这个池子重新算
    （与雷达「基本面名单」同一口径）。members 为 None 是全市场。自选因人而异，传 cacheable=False 不缓存。
    """
    latest: str | None = None
    use_cache = redis is not None and cacheable
    if redis is not None:
        try:
            raw = await redis.get(latest_key(market))
            latest = (raw.decode() if isinstance(raw, bytes) else raw) or None
            if use_cache and latest and (cached := await get_json(redis, _cache_key(market, latest, lang, scope))):
                return TrendRadarOut(**cached)
        except Exception as e:  # noqa: BLE001 缓存不可用退回查库
            logger.warning("quant_trend_radar_cache_read_failed", market=market, error=str(e))
    day, all_rows, ratings, ratings_down = await _market_inputs(market, lang, latest)
    rows = filter_rows(all_rows, members)
    tags = await load_sector_tags(market, redis) if rows else {}
    out = build_trend_radar(rows, market=market, as_of=day, tags=tags, ratings=ratings, ratings_down=ratings_down)
    if use_cache and redis is not None and day is not None and rows:
        try:
            await set_json(redis, _cache_key(market, day.isoformat(), lang, scope), out.model_dump(mode="json"),
                           expire=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_trend_radar_cache_write_failed", market=market, error=str(e))
    return out
