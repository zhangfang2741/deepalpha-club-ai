"""Rust 信号 dp_trend_legs 与 Python 参考实现（_in_trend / _trend_legs / leg_force）逐笔对照。

同一时刻、同一份结构（czsc 在该根 K 线上的快照）上两边必须完全一致：趋势前提、b / c 段是否取到、
两段的价差 / 量能 / 时长 / MACD 面积。只有自编译的 czsc（rust/czsc，带 dp_* 信号）才有 Rust 信号，
标准 PyPI 版自动跳过。改了 Rust 或 Python 任一边的取法，这条测试都会报警。
"""
from __future__ import annotations

import datetime as dt
import math
import random

import pytest
from czsc import BarGenerator, CzscSignals, Freq

from app.services.chan import signals as S
from app.services.chan.czsc_adapter import bars_to_raw_bars, czsc_macd, extract_structures
from app.services.chan.czsc_signals import _HAS_DP, _HAS_DP_LEGS, _dp_ts
from app.services.chan.leg_metric import leg_force

pytestmark = pytest.mark.skipif(not (_HAS_DP and _HAS_DP_LEGS), reason="需要自编译的 czsc（带 dp_* 信号）")

_L = Freq.D.value
_KEY = f"{_L}_D1趋势腿_DP辅助V261001"
_TK = f"{_L}_D1笔轨迹_DP辅助V261001"


def _walk(seed: int, n: int = 420) -> list[dict]:
    """带趋势 + 多周期震荡的随机行情，能反复形成中枢并产生趋势腿。"""
    rnd = random.Random(seed)
    price, out = 200.0, []
    for i in range(n):
        drift = -0.35 if (i // 140) % 2 == 0 else 0.35
        price = max(20.0, price + drift + 3.0 * math.sin(i / 5.0) + rnd.uniform(-2.0, 2.0))
        o = price + rnd.uniform(-1, 1)
        out.append({"time": (dt.date(2023, 1, 2) + dt.timedelta(days=i)).isoformat(),
                    "open": o, "high": max(o, price) + rnd.uniform(0, 1.5), "low": min(o, price) - rnd.uniform(0, 1.5),
                    "close": price, "volume": 1000 + rnd.randint(0, 800)})
    return out


def _compare(bars: list[dict]) -> tuple[int, int]:
    """返回（趋势成立的快照数, 取到两段的快照数）；有任何不一致直接断言失败。"""
    raw = bars_to_raw_bars(bars, symbol="T", freq=Freq.D)
    bg = BarGenerator(_L, [], max_count=len(raw) + 1)
    bg.init_freq_bars(_L, raw[:20])
    cs = CzscSignals(bg, [{"name": "dp_trend_legs_V261001", "freq": _L, "di": 1},
                          {"name": "dp_bi_track_V261001", "freq": _L, "di": 1}])
    prev, trend_n, legs_n = None, 0, 0
    for i, bar in enumerate(raw[20:], 20):
        cs.update_signals(bar)
        tk = cs.s[_TK]
        if tk == prev or tk.startswith("其他"):
            continue
        prev = tk
        st = extract_structures(cs.kas[_L], bars[:i + 1])
        strokes, pivots = st.strokes, st.stroke_pivots
        if len(strokes) < 2 or strokes[-1].end_time != _dp_ts(tk.split("_")[1]):
            continue
        last, is_buy = strokes[-1], strokes[-1].direction == "down"
        py_trend = S._in_trend(pivots, last.end_time, is_buy, last.end_price)
        legs = S._trend_legs(strokes, pivots, last.end_time, is_buy) if py_trend else None
        if legs is not None:  # 与 Rust 同口径：价格须越过 b 段终点（创新极值）
            b_end = legs[0][-1].end_price
            if (last.end_price >= b_end) if is_buy else (last.end_price <= b_end):
                py_trend = False
        v = cs.s[_KEY].split("_")
        rs_trend = v[0] in ("买趋势", "卖趋势")
        assert rs_trend == py_trend, (i, v[0], py_trend)
        if not rs_trend:
            continue
        trend_n += 1
        assert (legs is not None) == (v[1] != "无"), (i, v[1][:20], legs is not None)
        if legs is None:
            continue
        legs_n += 1
        mac = czsc_macd(cs.kas[_L])
        for leg, txt in ((legs[0], v[1]), (legs[1], v[2])):
            f = leg_force(leg, mac)
            got = [float(x) for x in txt.split("#")]
            exp = [f.price, f.volume, float(f.length), f.area]
            assert all(abs(a - e) <= 1e-9 * max(1.0, abs(e)) for a, e in zip(got, exp, strict=True)), (i, got, exp)
    return trend_n, legs_n


def test_rust_trend_legs_match_python_reference():
    total_trend = total_legs = 0
    for seed in (1, 2, 3, 4, 5, 6):
        t, g = _compare(_walk(seed))
        total_trend, total_legs = total_trend + t, total_legs + g
    # 不能是空对照：合成行情里必须真的出现过趋势成立 / 取到两段的快照
    assert total_trend >= 5 and total_legs >= 5, (total_trend, total_legs)
