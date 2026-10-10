"""基本面动向雷达：从最近一天批量结果里的动向事实（trend.py）挑出「最近在变好」的公司，按时间放进三圈。

- 预期上调（estimates）：本财年 EPS 一致预期近 7 天涨 ≥ 2% 放最内圈，否则近 30 天 ≥ 5% 放中圈，否则近 90 天 ≥ 10% 放外圈；
  覆盖分析师 ≥ 3 位才算（人太少一致预期会被一两位分析师带着跳）。
- 质地改善（quality）：最近一季披露在 90 天内，经营利润率或自由现金流利润率比上一季高 ≥ 1 个百分点，
  四项（营收同比 / 毛利率 / 经营利润率 / 自由现金流利润率）里至少两项变好，且没有一项变差超过 3 个百分点；按披露距今放圈（7 / 30 / 90 天）。
只陈列事实（谁在什么方面变好了、变了多少），不排名次、不是推荐；门槛随响应返回，App 推导说明直接用。
"""

from __future__ import annotations

from datetime import date

from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.quant_research import TrendFacts, TrendRadarItem, TrendRadarOut
from app.services.quant_research import repository as repo
from app.services.quant_research.batch import latest_key
from app.services.quant_research.builder import METHODOLOGY_VERSION
from app.services.quant_research.copy import Lang

RINGS = (7, 30, 90)
EPS_UP = {7: 0.02, 30: 0.05, 90: 0.10}
MIN_ANALYSTS = 3
QUALITY_MARGIN_PP = 1.0        # 经营利润率或自由现金流利润率至少提高这么多
QUALITY_IMPROVED_MIN = 2       # 四项里至少这么多项变好
QUALITY_WORST_PP = -3.0        # 任何一项变差不能超过这么多
QUALITY_EPS = 0.1              # 变化小于 0.1 个百分点视为没变
PER_KIND_LIMIT = 60
CACHE_TTL = 6 * 3600


def estimates_item(f: TrendFacts) -> tuple[int, float] | None:
    """(圈, 变化率)；不满足任何一圈返回 None。"""
    if f.n_analysts < MIN_ANALYSTS:
        return None
    for days, chg in ((7, f.eps_rev_7d), (30, f.eps_rev_30d), (90, f.eps_rev_90d)):
        if chg is not None and chg >= EPS_UP[days]:
            return days, chg
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


def build_trend_radar(rows: list[dict], *, market: str, as_of: date | None) -> TrendRadarOut:
    """rows：{symbol, name, grade, sector_name, trend(dict)}。"""
    est: list[TrendRadarItem] = []
    qual: list[TrendRadarItem] = []
    for r in rows:
        if not r.get("trend"):
            continue
        f = TrendFacts(**r["trend"])
        base = {"symbol": r["symbol"], "name": r.get("name"), "sector_name": r.get("sector_name"), "grade": r.get("grade")}
        if (e := estimates_item(f)) is not None:
            est.append(TrendRadarItem(**base, kind="estimates", ring_days=e[0], strength=round(e[1], 4), facts=f))
        if as_of is not None and (q := quality_item(f, as_of)) is not None:
            qual.append(TrendRadarItem(**base, kind="quality", ring_days=q[0], strength=q[1], facts=f))
    est.sort(key=lambda i: (i.ring_days, -i.strength))
    qual.sort(key=lambda i: (i.ring_days, -i.strength))
    est, qual = est[:PER_KIND_LIMIT], qual[:PER_KIND_LIMIT]
    thresholds = {f"eps_up_{d}d": v for d, v in EPS_UP.items()} | {
        "min_analysts": MIN_ANALYSTS, "quality_margin_pp": QUALITY_MARGIN_PP,
        "quality_improved_min": QUALITY_IMPROVED_MIN, "quality_worst_pp": QUALITY_WORST_PP}
    return TrendRadarOut(market=market, as_of=as_of.isoformat() if as_of else None, rings=list(RINGS),
                         thresholds=thresholds, items=est + qual,
                         counts={"estimates": len(est), "quality": len(qual)})


def _cache_key(market: str, as_of: str, lang: str) -> str:
    return f"quant:{market}:trend_radar:{METHODOLOGY_VERSION}:{as_of}:{lang}"


async def get_trend_radar(market: str, lang: Lang, *, redis: Redis | None) -> TrendRadarOut:
    """最近一天的动向雷达；整份结果按（方法版本, 批量日期, 语言）缓存 6 小时，新一天批量后自动换键。"""
    latest: str | None = None
    if redis is not None:
        try:
            raw = await redis.get(latest_key(market))
            latest = (raw.decode() if isinstance(raw, bytes) else raw) or None
            if latest and (cached := await get_json(redis, _cache_key(market, latest, lang))):
                return TrendRadarOut(**cached)
        except Exception as e:  # noqa: BLE001 缓存不可用退回查库
            logger.warning("quant_trend_radar_cache_read_failed", market=market, error=str(e))
    day, rows = await repo.trend_radar_rows(market, lang, as_of=date.fromisoformat(latest) if latest else None)
    out = build_trend_radar(rows, market=market, as_of=day)
    if redis is not None and day is not None and rows:
        try:
            await set_json(redis, _cache_key(market, day.isoformat(), lang), out.model_dump(mode="json"), expire=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_trend_radar_cache_write_failed", market=market, error=str(e))
    return out
