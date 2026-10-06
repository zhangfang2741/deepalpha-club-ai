"""基本面雷达：当前综合等级最高的前 N 只。"""
from datetime import date

from app.services.signal_radar import analyst_events as ae
from app.services.signal_radar import fundamental_top as ft
from app.services.signal_radar.quant_filter import QuantGrade


def _g(grade, score, as_of=date(2026, 10, 5), avail=None):
    return QuantGrade(grade, score, as_of, avail or as_of)


def test_rank_latest_uses_newest_row_then_grade_then_score():
    history = {
        "A": [_g("B", 50, date(2026, 10, 2)), _g("A+", 80, date(2026, 10, 5))],   # 取最新一行 A+
        "B": [_g("A+", 90)],
        "C": [_g("A", 70)],
        "D": [_g(None, None)],                                                   # 无等级丢弃
        "E": [_g("A+", 90)],
    }
    out = ft.rank_latest(history)
    assert [s for s, _ in out] == ["B", "E", "A", "C"]     # B/E 同分按代码；A(80)<90 排后；C 等级低


def test_rank_latest_same_day_later_write_wins():
    h = {"X": [_g("B", 50, avail=date(2026, 10, 5)), _g("A", 70, avail=date(2026, 10, 6))]}
    assert ft.rank_latest(h)[0][1].grade == "A"


def test_net_counts_window():
    acts = [
        {"date": "2026-10-02", "firm": "a", "prev": "", "new": "", "action": "upgrade"},
        {"date": "2026-10-01", "firm": "b", "prev": "", "new": "", "action": "upgrade"},
        {"date": "2026-09-01", "firm": "c", "prev": "", "new": "", "action": "downgrade"},   # 窗口外
        {"date": "2026-10-02", "firm": "d", "prev": "", "new": "", "action": "downgrade"},
    ]
    assert ae.net_counts(acts, date(2026, 9, 15)) == (2, 1)


async def test_unknown_universe_none():
    assert await ft.fundamental_top("us", "nope", redis=None) is None   # type: ignore[arg-type]


class _FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None, nx=False):
        self.kv[key] = value
        return True

    async def mget(self, keys):
        return [self.kv.get(k) for k in keys]


async def test_load_ranked_caches_second_call(monkeypatch):
    """第二次不再读库、不再解析成分股：好股票门槛与名单共用同一份缓存。"""
    import datetime as dt

    calls = {"repo": 0, "pairs": 0}

    async def fake_pairs(market, *, redis, universe_key):
        calls["pairs"] += 1
        return [("AAA", "甲"), ("BBB", "乙")]

    class Row:
        def __init__(self, symbol, grade, score):
            self.symbol, self.grade, self.score = symbol, grade, score

    async def fake_repo(market, symbols, start, end):
        calls["repo"] += 1
        return [Row("AAA", "A", 70.0), Row("BBB", "B", 55.0)]

    def fake_grade_from_row(row):
        return QuantGrade(row.grade, row.score, dt.date(2026, 10, 5), dt.date(2026, 10, 5), version="q6")

    monkeypatch.setattr(ft, "resolve_constituents", fake_pairs)
    monkeypatch.setattr(ft.repository, "get_latest_quant_grades", fake_repo)
    monkeypatch.setattr(ft, "grade_from_row", fake_grade_from_row)
    redis = _FakeRedis()
    end = dt.date(2026, 10, 6)
    first = await ft.load_ranked("us", "nasdaq100", redis, end)           # type: ignore[arg-type]
    second = await ft.load_ranked("us", "nasdaq100", redis, end)          # type: ignore[arg-type]
    assert calls == {"repo": 1, "pairs": 1}
    assert [(s, g.grade, g.score) for s, g in first[0]] == [(s, g.grade, g.score) for s, g in second[0]]
    assert second[1] == {"AAA": "甲", "BBB": "乙"}
    assert second[0][0][1].version == "q6" and second[0][0][1].as_of == dt.date(2026, 10, 5)


async def test_analyst_read_cache_uses_one_mget():
    import json

    redis = _FakeRedis()
    redis.kv[ae.cache_key("AAA")] = json.dumps({"at": "x", "actions": []})
    redis.kv[ae.cache_key("BAD")] = "not json"
    out = await ae._read_cache(redis, ["AAA", "BBB", "BAD"])               # type: ignore[arg-type]
    assert list(out) == ["AAA"]
