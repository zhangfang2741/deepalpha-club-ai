"""严格口径买卖点的结构不变量（性质测试）：在多组合成行情上，对每个产出的信号逐条核对它自己的定义。

手工用例锁住「已知答案」的场景，这里锁住「任何行情下都必须成立」的性质：落点、方向、二 / 三类与一类 / 中枢的关系、
同笔去重、时间顺序。标准 czsc 与自编译 czsc（Rust 信号）两条路径都跑。
"""
from __future__ import annotations

import datetime as dt
import functools
import math
import random

import pytest

from app.services.chan.analyzer import ChanAnalyzer

_BARS = 900
_SEEDS = range(1, 21)  # 20 组 × (原行情 + 价格镜像) = 40 次分析；样本太少性质测试会空跑


def _walk(seed: int, n: int = _BARS) -> list[dict]:
    """带趋势切换 + 多周期震荡的随机行情，反复形成中枢、趋势腿、离开与回抽。"""
    rnd = random.Random(seed)
    price, out = 200.0, []
    for i in range(n):
        drift = (-0.45, 0.45, -0.2, 0.6)[(i // 90) % 4]
        price = max(20.0, price + drift + 3.2 * math.sin(i / 5.5) + 1.4 * math.sin(i / 17.0) + rnd.uniform(-2.2, 2.2))
        o = price + rnd.uniform(-1, 1)
        out.append({"time": (dt.date(2022, 1, 3) + dt.timedelta(days=i)).isoformat(), "open": o,
                    "high": max(o, price) + rnd.uniform(0, 1.6), "low": min(o, price) - rnd.uniform(0, 1.6),
                    "close": price, "volume": 1000 + rnd.randint(0, 900)})
    return out


def _mirror(bars: list[dict], axis: float = 400.0) -> list[dict]:
    """价格上下翻转：跌势变涨势，使买点 / 卖点两侧都被覆盖。"""
    return [dict(b, open=axis - b["open"], close=axis - b["close"], high=axis - b["low"], low=axis - b["high"])
            for b in bars]


@functools.lru_cache(maxsize=1)
def _all_analyses() -> tuple:
    out = []
    for seed in _SEEDS:
        bars = _walk(seed)
        for tag, b in (("", bars), ("m", _mirror(bars))):
            out.append((f"{seed}{tag}", b, ChanAnalyzer().analyze(f"S{seed}{tag}", b, mode="strict")))
    return tuple(out)


def _analyses():
    yield from _all_analyses()


def test_every_signal_lands_on_a_finished_stroke_end_in_the_right_direction():
    n = 0
    for seed, _, r in _analyses():
        by_end = {s.end_time: s for s in r.strokes}
        for x in r.signals:
            st = by_end.get(x.time)
            assert st is not None, (seed, x.type, x.time, "信号不在任何笔的终点")
            assert x.price == pytest.approx(st.end_price) or x.type in ("buy1", "sell1"), (seed, x.type, x.time)
            # 买点只落下降笔终点、卖点只落上升笔终点
            assert st.direction == ("down" if x.is_buy else "up"), (seed, x.type, x.time)
            n += 1
    assert n >= 40, n  # 不能是空对照


def test_type2_always_follows_a_surviving_type1_and_never_breaks_its_extreme():
    n = 0
    for seed, _, r in _analyses():
        idx = {s.end_time: i for i, s in enumerate(r.strokes)}
        ones = {(x.type, x.time): x for x in r.signals if x.type in ("buy1", "sell1")}
        for x in r.signals:
            if x.type not in ("buy2", "sell2"):
                continue
            src = "buy1" if x.type == "buy2" else "sell1"
            i = idx[x.time] - 2  # 二类是一类所在笔之后第二笔（第一次回落 / 反弹）
            assert i >= 0
            one = ones.get((src, r.strokes[i].end_time))
            assert one is not None, (seed, x.type, x.time, "二类前面没有同方向一类")
            # 不破一类极值（买：回落终点高于一买价；卖：反弹终点低于一卖价）
            assert (x.price > one.price) if x.is_buy else (x.price < one.price), (seed, x.type, x.time)
            n += 1
    assert n >= 3, n


def test_type3_stays_outside_some_pivot_it_left_and_is_not_inside_it():
    n = 0
    for seed, _, r in _analyses():
        for x in r.signals:
            if x.type not in ("buy3", "sell3"):
                continue
            # 三买：回落低点高于某个中枢上沿；三卖：反弹高点低于某个中枢下沿（该中枢在信号之前开始）
            ok = any(p.start_time < x.time and ((x.price > p.zg) if x.is_buy else (x.price < p.zd))
                     for p in r.stroke_pivots)
            assert ok, (seed, x.type, x.time, x.price)
            n += 1
    assert n >= 3, n


def test_no_type2_and_type3_on_the_same_stroke_and_times_are_ordered():
    for seed, bars, r in _analyses():
        by_time: dict[str, set[str]] = {}
        for x in r.signals:
            by_time.setdefault(x.time, set()).add(x.type)
        for t, types in by_time.items():
            assert not ({"buy2", "buy3"} <= types or {"sell2", "sell3"} <= types), (seed, t, types)
        keys = [(x.time, x.type) for x in r.signals]
        assert keys == sorted(keys), seed
        last = bars[-1]["time"]
        for x in r.signals:
            # 成立日不早于所在笔终点、不晚于最后一根 K 线（未来的成立日会让信号「提前」可见）
            assert x.detected_time == "" or x.time <= x.detected_time <= last, (seed, x.type, x.time, x.detected_time)


def test_candidates_never_leak_into_signals():
    for seed, _, r in _analyses():
        signal_keys = {(x.type, x.time) for x in r.signals}
        assert all(c.confirmed is False for c in r.candidate_signals), seed
        assert not signal_keys & {(c.type, c.time) for c in r.candidate_signals}, seed


def test_property_tests_are_not_vacuous():
    """每一类买卖点在样本里都要出现过，否则上面的不变量对它就是空跑。"""
    seen = {t: 0 for t in ("buy1", "sell1", "buy2", "sell2", "buy3", "sell3")}
    for _, _, r in _analyses():
        for x in r.signals:
            seen[x.type] += 1
    assert all(v >= 1 for v in seen.values()), seen
