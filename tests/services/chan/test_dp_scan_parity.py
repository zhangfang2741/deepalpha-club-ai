"""Rust 整段扫描（dp_scan_bs）与 Python 逐根循环必须逐位一致：事件、笔完成表、成笔时刻表。

只有自编译的 czsc（rust/czsc）才有 dp_scan_bs，标准 PyPI 版自动跳过。覆盖日线 / 周线 / 30 分钟（带时分的
时间字符串是解析最容易出错的地方），严格（只启用一类 + 趋势腿）与宽松（一二三类）两种族配置，以及原生出错时的退回。
"""
from __future__ import annotations

import datetime as dt

import pytest
from czsc import Freq

from app.services.chan import czsc_signals as C
from tests.services.chan.test_strict_signal_invariants import _mirror, _walk

pytestmark = pytest.mark.skipif(not C._HAS_DP_SCAN, reason="需要自编译的 czsc（带 dp_scan_bs）")

_FAMILIES = (("first",), ("first", "second", "third"))


def _intraday(bars: list[dict]) -> list[dict]:
    """把日线行情改成 30 分钟线时间戳（每天 13 根：09:30 起），时间字符串带时分。"""
    out = []
    for i, b in enumerate(bars):
        day = dt.date(2024, 1, 2) + dt.timedelta(days=i // 13)
        t = dt.datetime.combine(day, dt.time(9, 30)) + dt.timedelta(minutes=30 * (i % 13))
        out.append(dict(b, time=t.strftime("%Y-%m-%d %H:%M")))
    return out


def _both(bars: list[dict], freq: Freq, families, monkeypatch):
    res = []
    for native in (True, False):
        monkeypatch.setattr(C, "_HAS_DP_SCAN", native)
        done: dict[str, str] = {}
        started: dict[str, str] = {}
        ev = C.scan_bs_events(bars, symbol="T", freq=freq, stroke_done_at=done, stroke_started_at=started,
                              families=families)
        res.append((ev, done, started))
    return res


@pytest.mark.parametrize("families", _FAMILIES)
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_native_scan_matches_python_loop_daily(seed, families, monkeypatch):
    for bars in (_walk(seed), _mirror(_walk(seed))):
        native, loop = _both(bars, Freq.D, families, monkeypatch)
        assert native == loop


@pytest.mark.parametrize("families", _FAMILIES)
def test_native_scan_matches_python_loop_intraday_and_weekly(families, monkeypatch):
    bars = _walk(3)
    native, loop = _both(_intraday(bars), Freq.F30, families, monkeypatch)
    assert native == loop
    # 30 分钟线的笔时间表里必须真出现带时分的时间（否则时间格式的对照是空的）
    assert any(" " in k for k in loop[1])
    weekly = [dict(b, time=(dt.date(2015, 1, 5) + dt.timedelta(weeks=i)).isoformat()) for i, b in enumerate(bars)]
    native, loop = _both(weekly, Freq.W, families, monkeypatch)
    assert native == loop


def test_native_scan_is_not_vacuous(monkeypatch):
    """对照的行情里必须真有事件，否则「一致」毫无意义。"""
    total = 0
    for seed in range(1, 7):
        native, loop = _both(_walk(seed), Freq.D, ("first", "second", "third"), monkeypatch)
        assert native == loop
        total += len(loop[0])
    assert total >= 20, total


def test_native_scan_falls_back_when_it_fails(monkeypatch):
    """原生路径出任何错（如无法解析的时间）都退回逐根循环，不抛异常、结果不丢。"""
    bars = _walk(2)
    expect = _both(bars, Freq.D, ("first",), monkeypatch)[1]
    monkeypatch.setattr(C, "_HAS_DP_SCAN", True)
    import czsc._native as native

    def boom(*a, **k):
        raise ValueError("模拟原生失败")

    monkeypatch.setattr(native, "dp_scan_bs", boom, raising=False)
    done: dict[str, str] = {}
    started: dict[str, str] = {}
    ev = C.scan_bs_events(bars, symbol="T", freq=Freq.D, stroke_done_at=done, stroke_started_at=started,
                          families=("first",))
    assert (ev, done, started) == expect


def test_native_scan_short_input_returns_empty():
    done: dict[str, str] = {}
    assert C.scan_bs_events(_walk(1)[:15], symbol="T", freq=Freq.D, stroke_done_at=done, families=("first",)) == []
    assert done == {}
