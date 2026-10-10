"""同阶段综合分排名：点企业阶段时列出该阶段综合分最高的若干家公司，并标出本股的位置。

只读最近一天的批量结果（样本内股票）；样本外股票（按需计算的）不在列表里，按它自己的综合分估算位置。
只陈列本模型的综合分，不构成推荐；文案见 iOS 端。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.quant_research import StageRankingItem, StageRankingOut, StageRankingSelf
from app.services.quant_research import repository as repo
from app.services.quant_research.copy import Lang

RANKING_LIMIT_MAX = 50


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


async def get_stage_ranking(market: str, stage: str, lang: Lang, *, symbol: str | None, score: float | None,
                            limit: int) -> StageRankingOut:
    """最近一天该阶段的排名（样本内股票）。"""
    as_of, rows = await repo.stage_ranking_rows(market, stage, lang)
    return build_stage_ranking([RankRow(*r) for r in rows], stage, market=market,
                               as_of=as_of.isoformat() if as_of else None, symbol=symbol, score=score,
                               limit=min(limit, RANKING_LIMIT_MAX))
