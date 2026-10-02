"""Rust 建结构 + 提取（dp_structures / dp_macd）与原 Python 实现（build_czsc + extract_structures + czsc_macd）对照。

结构（合并 K 线 / 分型 / 笔 / 笔级中枢）的数据类必须逐项相等，对象关系（相邻笔共享端点分型对象）也要一致，
MACD 逐位相等，整条 analyze 的结果在两条路径下完全相同。只有自编译的 czsc（带 dp_structures）才有 Rust 版，
标准 PyPI 版自动跳过。
"""
from __future__ import annotations

import datetime as dt

import pytest
from dataclasses import replace
from czsc import Freq

from app.services.chan import czsc_adapter as A
from app.services.chan import divergence as DV
from app.services.chan.analyzer import ChanAnalyzer
from tests.services.chan.test_strict_signal_invariants import _mirror, _walk

pytestmark = pytest.mark.skipif(not A._HAS_DP_STRUCT, reason="需要自编译的 czsc（带 dp_structures）")


def _py(bars, freq):
    c = A.build_czsc(bars, symbol="T", freq=freq)
    return A.extract_structures(c, bars), A.czsc_macd(c)


def _rs(bars, freq):
    import czsc._native as native

    return A._from_native(native.dp_structures(
        "T", freq.value, [b["time"] for b in bars], [float(b["open"]) for b in bars], [float(b["high"]) for b in bars],
        [float(b["low"]) for b in bars], [float(b["close"]) for b in bars], [float(b["volume"]) for b in bars]))


def _intraday(bars):
    out = []
    for i, b in enumerate(bars):
        day = dt.date(2024, 1, 2) + dt.timedelta(days=i // 13)
        t = dt.datetime.combine(day, dt.time(9, 30)) + dt.timedelta(minutes=30 * (i % 13))
        out.append(dict(b, time=t.strftime("%Y-%m-%d %H:%M")))
    return out


def _weekly(bars):
    return [dict(b, time=(dt.date(2015, 1, 5) + dt.timedelta(weeks=i)).isoformat()) for i, b in enumerate(bars)]


def _cases():
    for seed in range(1, 7):
        w = _walk(seed)
        yield f"d{seed}", w, Freq.D
        yield f"m{seed}", _mirror(w), Freq.D
    yield "30min", _intraday(_walk(3)), Freq.F30
    yield "weekly", _weekly(_walk(4)), Freq.W


def _assert_macd_close(a, b):
    """Rust 版 czsc 的 Rust MACD 与 Python 回退差在浮点尾数（~1e-13），1e-9 内视为一致。"""
    assert a.times == b.times
    for x, y in ((a.dif, b.dif), (a.dea, b.dea), (a.bar, b.bar)):
        assert len(x) == len(y) and all(abs(u - v) <= 1e-9 for u, v in zip(x, y, strict=True))


@pytest.mark.parametrize("name,bars,freq", list(_cases()), ids=lambda v: v if isinstance(v, str) else "")
def test_structures_and_macd_equal_python_implementation(name, bars, freq):
    (ps, pm), (rs, rm) = _py(bars, freq), _rs(bars, freq)
    assert rs.merged_candles == ps.merged_candles
    assert rs.fractals == ps.fractals
    assert rs.strokes == ps.strokes
    assert rs.stroke_pivots == ps.stroke_pivots
    _assert_macd_close(rm, pm)


def test_object_relationships_match_the_python_implementation():
    """相邻笔共享同一个端点分型对象；分型的左 / 中 / 右 K 线是独立对象，不与 merged_candles 共用；中枢元素就是笔对象。"""
    for seed in (1, 2, 3):
        rs, _ = _rs(_walk(seed), Freq.D)
        shared = 0
        for a, b in zip(rs.strokes, rs.strokes[1:], strict=False):
            if a.end_time == b.start_time:
                assert a.end is b.start
                shared += 1
        merged_ids = {id(c) for c in rs.merged_candles}
        for f in rs.fractals:
            assert not {id(f.candle), id(f.left), id(f.right)} & merged_ids
        for p in rs.stroke_pivots:
            assert all(any(e is s for s in rs.strokes) for e in p.elements)
        assert shared >= 5


def test_the_comparison_is_not_vacuous():
    n_strokes = n_pivots = 0
    for seed in range(1, 7):
        rs, _ = _rs(_walk(seed), Freq.D)
        n_strokes += len(rs.strokes)
        n_pivots += len(rs.stroke_pivots)
    assert n_strokes >= 60 and n_pivots >= 6, (n_strokes, n_pivots)


@pytest.mark.parametrize("n", [0, 1, 10, 25, 26, 27, 100, 900])
def test_native_calc_macd_equals_python_for_all_lengths(n, monkeypatch):
    bars = _walk(1)[:n] if n else []
    native = DV.calc_macd(bars)
    monkeypatch.setattr(DV, "_dp_macd", None)
    py = DV.calc_macd(bars)
    _assert_macd_close(native, py)


def test_build_structures_falls_back_when_native_fails(monkeypatch):
    import czsc._native as native

    bars = _walk(2)
    expect = _py(bars, Freq.D)

    def boom(*a, **k):
        raise ValueError("模拟原生失败")

    monkeypatch.setattr(native, "dp_structures", boom)
    got = A.build_structures(bars, symbol="T", freq=Freq.D)
    assert got[0] == expect[0] and got[1] == expect[1]


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
@pytest.mark.parametrize("mode", ["strict", "loose"])
def test_whole_analysis_is_identical_on_both_paths(seed, mode, monkeypatch):
    bars = _walk(seed)
    native = ChanAnalyzer().analyze("T", bars, mode=mode)
    monkeypatch.setattr(A, "_HAS_DP_STRUCT", False)
    monkeypatch.setattr(DV, "_dp_macd", None)
    py = ChanAnalyzer().analyze("T", bars, mode=mode)
    _assert_macd_close(native.macd, py.macd)
    assert replace(native, macd=py.macd) == py
    assert native.strokes and native.stroke_pivots
