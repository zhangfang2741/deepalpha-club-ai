"""同阶段综合分排名：排序、本股位置（样本内 / 样本外按分数估算）、条数上限。"""

from app.services.quant_research.ranking import RankRow, build_stage_ranking


def _rows(n):
    return [RankRow(f"S{i:02d}", f"Name{i}", "B" if i < 5 else "C", 90.0 - i, "信息技术") for i in range(n)]


def test_ranking_sorted_and_limited():
    out = build_stage_ranking(_rows(40), "growth", market="us", as_of="2026-10-09", symbol=None, score=None, limit=30)
    assert out.cohort_size == 40 and len(out.items) == 30
    assert [i.rank for i in out.items[:3]] == [1, 2, 3]
    assert out.items[0].symbol == "S00" and out.items[0].score == 90.0
    assert out.self_item is None


def test_self_in_cohort_outside_top():
    out = build_stage_ranking(_rows(40), "growth", market="us", as_of="2026-10-09", symbol="s35", score=None, limit=30)
    assert out.self_item is not None and out.self_item.rank == 36 and out.self_item.in_universe
    assert not any(i.is_self for i in out.items)


def test_self_in_top_is_flagged():
    out = build_stage_ranking(_rows(40), "growth", market="us", as_of="2026-10-09", symbol="S02", score=None, limit=30)
    assert out.items[2].is_self and out.self_item is not None and out.self_item.rank == 3


def test_self_outside_universe_estimated_by_score():
    out = build_stage_ranking(_rows(40), "growth", market="us", as_of="2026-10-09", symbol="SNOW", score=70.5, limit=30)
    # 分数 90..51，高于 70.5 的有 20 家 → 估算排第 21
    assert out.self_item is not None and out.self_item.rank == 21 and not out.self_item.in_universe
    assert out.self_item.total == 41


def test_empty_cohort():
    out = build_stage_ranking([], "decline", market="us", as_of=None, symbol="X", score=10.0, limit=30)
    assert out.cohort_size == 0 and out.items == [] and out.self_item is None


class _FakeRedis:
    def __init__(self, latest):
        self.store = {"quant:us:latest_as_of": latest} if latest else {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


async def test_rows_cached_per_stage_and_reused(monkeypatch):
    from datetime import date

    from app.services.quant_research import ranking

    calls = []

    async def fake_rows(market, stage, lang, as_of=None):
        calls.append(as_of)
        return date(2026, 10, 9), [("AAA", "A", "B", 80.0, "IT"), ("BBB", "B", "C", 60.0, "IT")]

    monkeypatch.setattr(ranking.repo, "stage_ranking_rows", fake_rows)
    redis = _FakeRedis("2026-10-09")
    a = await ranking.get_stage_ranking("us", "growth", "zh", symbol="BBB", score=None, limit=30, redis=redis)
    b = await ranking.get_stage_ranking("us", "growth", "zh", symbol="AAA", score=None, limit=30, redis=redis)
    assert len(calls) == 1 and calls[0] == date(2026, 10, 9)        # 第二次走缓存，不再查库
    assert a.self_item.rank == 2 and b.self_item.rank == 1           # 本股名次每次现算
    assert b.as_of == "2026-10-09" and b.items[0].symbol == "AAA"


async def test_without_redis_falls_back_to_db(monkeypatch):
    from datetime import date

    from app.services.quant_research import ranking

    async def fake_rows(market, stage, lang, as_of=None):
        return date(2026, 10, 9), [("AAA", "A", "B", 80.0, "IT")]

    monkeypatch.setattr(ranking.repo, "stage_ranking_rows", fake_rows)
    out = await ranking.get_stage_ranking("us", "growth", "zh", symbol=None, score=None, limit=30, redis=None)
    assert out.cohort_size == 1
