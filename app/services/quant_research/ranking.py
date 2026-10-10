"""同阶段综合分排名：点企业阶段时列出该阶段综合分最高的若干家公司，并标出本股的位置。

只读最近一天的批量结果（样本内股票）；样本外股票（按需计算的）不在列表里，按它自己的综合分估算位置。
只陈列本模型的综合分，不构成推荐；文案见 iOS 端。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.quant_research import StageRankingItem, StageRankingOut, StageRankingSelf
from app.services.quant_research import repository as repo
from app.services.quant_research.batch import latest_key
from app.services.quant_research.builder import METHODOLOGY_VERSION
from app.services.quant_research.copy import Lang

RANKING_LIMIT_MAX = 50
CACHE_TTL = 6 * 3600   # 键里带批量日期与方法版本：新一天批量跑完或改规则后自动换键


@dataclass(frozen=True)
class RankRow:
    symbol: str
    name: str | None
    grade: str | None
    score: float
    sector_name: str | None


def build_stage_ranking(rows: list[RankRow], stage: str, *, market: str, as_of: str | None, symbol: str | None,
                        score: float | None, limit: int) -> StageRankingOut:
    """按综合分从高到低排；本股在样本内取实际名次，样本外按 score 估算（比它高的家数 + 1）。"""
    ranked = sorted(rows, key=lambda r: (-r.score, r.symbol))
    sym = symbol.upper() if symbol else None
    items = [StageRankingItem(rank=i + 1, symbol=r.symbol, name=r.name, grade=r.grade, score=round(r.score, 1),
                              sector_name=r.sector_name, is_self=r.symbol == sym)
             for i, r in enumerate(ranked[:limit])]
    self_item = None
    if sym and ranked:
        pos = next((i for i, r in enumerate(ranked) if r.symbol == sym), None)
        if pos is not None:
            self_item = StageRankingSelf(rank=pos + 1, total=len(ranked), in_universe=True)
        elif score is not None:
            self_item = StageRankingSelf(rank=sum(r.score > score for r in ranked) + 1, total=len(ranked) + 1,
                                         in_universe=False)
    return StageRankingOut(market=market, stage=stage, as_of=as_of, cohort_size=len(ranked), items=items,
                           self_item=self_item)


def _cache_key(market: str, as_of: str, stage: str, lang: str) -> str:
    return f"quant:{market}:stage_rank:{METHODOLOGY_VERSION}:{as_of}:{stage}:{lang}"


async def _latest_as_of(redis: Redis | None, market: str) -> str | None:
    """批量跑完写在 Redis 的最近日期（读不到返回 None，退回查库）。"""
    if redis is None:
        return None
    try:
        raw = await redis.get(latest_key(market))
    except Exception as e:  # noqa: BLE001 缓存读失败退回查库
        logger.warning("quant_stage_rank_latest_failed", market=market, error=str(e))
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    return raw or None


async def _load_rows(market: str, stage: str, lang: Lang, redis: Redis | None) -> tuple[str | None, list[RankRow]]:
    """该阶段全部有综合分的股票：先读缓存（整阶段一份，和本股无关），没有再查库并写缓存。"""
    as_of = await _latest_as_of(redis, market)
    if redis is not None and as_of:
        try:
            cached = await get_json(redis, _cache_key(market, as_of, stage, lang))
            if cached:
                return cached["as_of"], [RankRow(**r) for r in cached["rows"]]
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_stage_rank_cache_read_failed", market=market, stage=stage, error=str(e))
    day, raw = await repo.stage_ranking_rows(market, stage, lang, as_of=date.fromisoformat(as_of) if as_of else None)
    rows = [RankRow(*r) for r in raw]
    day_s = day.isoformat() if day else None
    if redis is not None and day_s and rows:
        try:
            await set_json(redis, _cache_key(market, day_s, stage, lang),
                           {"as_of": day_s, "rows": [asdict(r) for r in rows]}, expire=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_stage_rank_cache_write_failed", market=market, stage=stage, error=str(e))
    return day_s, rows


async def get_stage_ranking(market: str, stage: str, lang: Lang, *, symbol: str | None, score: float | None,
                            limit: int, redis: Redis | None = None) -> StageRankingOut:
    """最近一天该阶段的排名（样本内股票）；整阶段的排序数据缓存 6 小时，本股名次每次现算（很快）。"""
    as_of, rows = await _load_rows(market, stage, lang, redis)
    return build_stage_ranking(rows, stage, market=market, as_of=as_of, symbol=symbol, score=score,
                               limit=min(limit, RANKING_LIMIT_MAX))
