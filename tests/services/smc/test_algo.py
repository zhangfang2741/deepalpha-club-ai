"""SMC（Smart Money Concepts）算法：摆动点、BOS / CHoCH、订单块、公允价值缺口、等高低点、流动性扫荡、
溢价折价区、强弱高低点、前周期高低点。全部用手工构造的 K 线验证定义。"""
from __future__ import annotations

from app.services.smc import algo


def _bars(points: list[float], *, start: str = "2025-01-01", pad: float = 0.2, vol: float = 100.0) -> list[dict]:
    """沿折线逐根生成 K 线：每根开盘 = 上一根收盘，收盘 = 折线上的值，影线各外延 pad。"""
    from datetime import date, timedelta

    d0 = date.fromisoformat(start)
    out: list[dict] = []
    prev = points[0]
    for i, c in enumerate(points):
        o = prev
        out.append({
            "time": (d0 + timedelta(days=i)).isoformat(),
            "open": o, "close": c,
            "high": max(o, c) + pad, "low": min(o, c) - pad,
            "volume": vol,
        })
        prev = c
    return out


def _line(*knots: float, step: float = 1.0) -> list[float]:
    """把拐点连成逐根上涨 / 下跌的折线（每根最多动 step）。"""
    pts = [knots[0]]
    for a, b in zip(knots, knots[1:]):
        n = max(1, int(round(abs(b - a) / step)))
        for k in range(1, n + 1):
            pts.append(a + (b - a) * k / n)
    return pts


# ── 摆动点 ──────────────────────────────────────────────────────────────

def test_find_swings_marks_local_extremes():
    bars = _bars(_line(10, 20, 12, 25, 15))
    sw = algo.find_swings(bars, 3)
    highs = [s.price for s in sw if s.kind == "high"]
    lows = [s.price for s in sw if s.kind == "low"]
    assert any(abs(h - 20.2) < 1e-6 for h in highs)
    assert any(abs(h - 25.2) < 1e-6 for h in highs)
    assert any(abs(l - 11.8) < 1e-6 for l in lows)


# ── 结构突破 BOS / 转变 CHoCH ──────────────────────────────────────────

def test_bullish_bos_when_uptrend_breaks_previous_swing_high():
    # 10→20→14→26：第二个高点越过第一个高点（20）
    bars = _bars(_line(10, 20, 14, 26, 18))
    res = algo.analyze(bars, swing_len=3)
    bulls = [b for b in res.breaks if b.direction == "bull"]
    assert bulls, "应出现向上突破"
    # 第一次向上突破前没有趋势 → BOS（建立趋势）
    assert bulls[0].kind == "bos"
    assert bulls[0].level == algo_level_high(bars, 20)
    assert bulls[0].break_idx > bulls[0].level_idx


def algo_level_high(bars: list[dict], price: float) -> float:
    return max(b["high"] for b in bars if abs(b["high"] - (price + 0.2)) < 1e-6)


def test_choch_when_break_goes_against_the_trend():
    # 先上行建立多头结构，再跌破最近的摆动低点 → 向下的 CHoCH
    bars = _bars(_line(10, 20, 14, 26, 18, 8))
    res = algo.analyze(bars, swing_len=3)
    kinds = [(b.kind, b.direction) for b in res.breaks]
    assert ("bos", "bull") in kinds
    assert ("choch", "bear") in kinds
    assert res.trend == "bear"


def test_continuation_break_is_bos_not_choch():
    # 多头里连续越过前高：第二次也是 BOS
    bars = _bars(_line(10, 20, 14, 26, 19, 32, 24))
    res = algo.analyze(bars, swing_len=3)
    bulls = [b for b in res.breaks if b.direction == "bull"]
    assert len(bulls) >= 2
    assert all(b.kind == "bos" for b in bulls)


def test_structure_has_no_lookahead():
    """只用「已确认」的摆动点：截掉后面的 K 线，已经出现过的突破一个不能变。"""
    bars = _bars(_line(10, 20, 14, 26, 18, 8, 15, 5))
    full = algo.analyze(bars, swing_len=3)
    for cut in range(10, len(bars)):
        part = algo.analyze(bars[:cut], swing_len=3)
        expect = [(b.kind, b.direction, b.level_idx, b.break_idx) for b in full.breaks if b.break_idx < cut]
        got = [(b.kind, b.direction, b.level_idx, b.break_idx) for b in part.breaks]
        assert got == expect, f"cut={cut}"


# ── 订单块 ──────────────────────────────────────────────────────────────

def test_bullish_order_block_is_lowest_candle_before_the_break():
    bars = _bars(_line(10, 20, 14, 26, 18))
    res = algo.analyze(bars, swing_len=3)
    b = next(b for b in res.breaks if b.direction == "bull")
    ob = next(o for o in res.order_blocks if o.direction == "bull")
    seg = range(b.level_idx, b.break_idx)
    lowest = min(seg, key=lambda i: (bars[i]["low"], -i))
    assert ob.idx == lowest
    assert ob.top == bars[lowest]["high"] and ob.bottom == bars[lowest]["low"]
    assert ob.top > ob.bottom


def test_order_block_is_mitigated_when_close_breaks_through_it():
    bars = _bars(_line(10, 20, 14, 26, 18, 8))
    res = algo.analyze(bars, swing_len=3)
    ob = next(o for o in res.order_blocks if o.direction == "bull")
    assert ob.mitigated_idx is not None
    assert bars[ob.mitigated_idx]["close"] < ob.bottom
    # 之前没有任何一根收盘跌破过
    assert all(bars[j]["close"] >= ob.bottom for j in range(ob.break_idx + 1, ob.mitigated_idx))


def test_unmitigated_order_block_stays_open():
    bars = _bars(_line(10, 20, 14, 26, 22))
    res = algo.analyze(bars, swing_len=3)
    ob = next(o for o in res.order_blocks if o.direction == "bull")
    assert ob.mitigated_idx is None


# ── 公允价值缺口 ────────────────────────────────────────────────────────

def _gap_bars(up: bool = True) -> list[dict]:
    # 先是 20 根小波动（建立「平均实体」），再来三根：第三根与第一根之间留下缺口
    bars = _bars([100 + (0.3 if i % 2 else -0.3) for i in range(20)])
    t = len(bars)

    def add(o, h, l, c, i):
        bars.append({"time": f"2025-02-{i:02d}", "open": o, "high": h, "low": l, "close": c, "volume": 100.0})

    if up:
        add(100, 100.6, 99.6, 100.2, 1)       # 第一根：高点 100.6
        add(100.2, 104.5, 100.1, 104.0, 2)    # 大阳线
        add(104.0, 105.0, 102.0, 104.5, 3)    # 第三根：低点 102.0 > 100.6 → 缺口 100.6~102.0
    else:
        add(100, 100.4, 99.4, 99.8, 1)
        add(99.8, 99.9, 95.5, 96.0, 2)
        add(96.0, 98.0, 95.0, 95.5, 3)        # 第三根高点 98.0 < 99.4 → 缺口 98.0~99.4
    assert len(bars) == t + 3
    return bars


def test_bullish_fvg_zone_and_open_state():
    bars = _gap_bars(up=True)
    res = algo.analyze(bars, swing_len=3)
    g = next(f for f in res.fvgs if f.direction == "bull")
    assert (g.bottom, g.top) == (100.6, 102.0)
    assert g.idx == len(bars) - 2           # 起点 = 中间那根大阳线
    assert g.filled_idx is None


def test_bearish_fvg_zone():
    bars = _gap_bars(up=False)
    res = algo.analyze(bars, swing_len=3)
    g = next(f for f in res.fvgs if f.direction == "bear")
    assert (g.bottom, g.top) == (98.0, 99.4)


def test_fvg_is_filled_when_price_trades_back_through_it():
    bars = _gap_bars(up=True)
    bars.append({"time": "2025-02-04", "open": 104.5, "high": 104.6, "low": 100.0, "close": 100.5, "volume": 100.0})
    res = algo.analyze(bars, swing_len=3)
    g = next(f for f in res.fvgs if f.direction == "bull")
    assert g.filled_idx == len(bars) - 1


def test_tiny_gap_with_small_candle_is_ignored():
    # 中间那根不是大实体：不算（LuxAlgo 的自动阈值：实体须明显大于平均实体）
    bars = _bars([100 + (0.3 if i % 2 else -0.3) for i in range(20)])
    bars += [
        {"time": "2025-02-01", "open": 100, "high": 100.1, "low": 99.9, "close": 100.05, "volume": 100.0},
        {"time": "2025-02-02", "open": 100.05, "high": 100.5, "low": 100.2, "close": 100.4, "volume": 100.0},
        {"time": "2025-02-03", "open": 100.4, "high": 100.8, "low": 100.3, "close": 100.7, "volume": 100.0},
    ]
    assert not [f for f in algo.analyze(bars, swing_len=3).fvgs if f.idx >= 20]


# ── 等高点 / 等低点 ─────────────────────────────────────────────────────

def test_equal_highs_detected_within_atr_tolerance():
    # 两个几乎一样高的高点（20.2 与 20.25）
    pts = _line(10, 20, 13, 20.05, 12)
    bars = _bars(pts)
    res = algo.analyze(bars, swing_len=3)
    assert any(e.kind == "eqh" for e in res.equal_levels)


def test_clearly_different_highs_are_not_equal():
    bars = _bars(_line(10, 20, 13, 26, 12))
    res = algo.analyze(bars, swing_len=3)
    assert not [e for e in res.equal_levels if e.kind == "eqh"]


# ── 流动性扫荡 ──────────────────────────────────────────────────────────

def test_sweep_wick_beyond_swing_high_and_close_back_inside():
    bars = _bars(_line(10, 20, 14, 19))
    lvl = max(b["high"] for b in bars)       # 第一个摆动高点 20.2
    n = len(bars)
    bars.append({"time": "2025-03-01", "open": 19.0, "high": lvl + 1.5, "low": 18.5, "close": 19.2, "volume": 100.0})
    bars += _bars(_line(19.2, 15), start="2025-03-02")[1:]
    res = algo.analyze(bars, swing_len=3)
    sw = [s for s in res.sweeps if s.side == "high"]
    assert sw and sw[0].idx == n
    assert abs(sw[0].level - lvl) < 1e-6


def test_close_beyond_level_is_a_break_not_a_sweep():
    bars = _bars(_line(10, 20, 14, 26, 18))
    res = algo.analyze(bars, swing_len=3)
    b = next(b for b in res.breaks if b.direction == "bull")
    assert not [s for s in res.sweeps if s.side == "high" and s.level == b.level and s.idx == b.break_idx]


# ── 溢价 / 折价、强弱高低点 ────────────────────────────────────────────

def test_premium_discount_zone_uses_trailing_extremes():
    bars = _bars(_line(10, 20, 14, 26, 18))
    res = algo.analyze(bars, swing_len=3)
    z = res.zone
    assert z is not None
    assert z.top > z.equilibrium > z.bottom
    assert abs(z.equilibrium - (z.top + z.bottom) / 2) < 1e-9
    assert z.end_idx == len(bars) - 1


def test_strong_weak_labels_follow_trend():
    up = algo.analyze(_bars(_line(10, 20, 14, 26, 18)), swing_len=3)
    assert up.trend == "bull"
    assert up.extremes.low.strength == "strong" and up.extremes.high.strength == "weak"
    down = algo.analyze(_bars(_line(30, 20, 26, 12, 22)), swing_len=3)
    assert down.trend == "bear"
    assert down.extremes.high.strength == "strong" and down.extremes.low.strength == "weak"


# ── 前周期高低点 ────────────────────────────────────────────────────────

def test_previous_week_and_month_levels_for_daily():
    # 2025-01-01（周三）起连续 60 天：上一周、上一个月的高低点
    bars = _bars(_line(10, 30, 15, 40, 20, 35, step=1.0), start="2025-01-01")
    lv = {k.code: k for k in algo.key_levels(bars, "daily")}
    assert {"PWH", "PWL", "PMH", "PML"} <= set(lv)
    cur_day = bars[-1]["time"]
    from datetime import date
    cur = date.fromisoformat(cur_day)
    wk = cur.isocalendar()[:2]
    prev_week = [b for b in bars if date.fromisoformat(b["time"]).isocalendar()[:2] < wk]
    last_wk = max(date.fromisoformat(b["time"]).isocalendar()[:2] for b in prev_week)
    pw = [b for b in bars if date.fromisoformat(b["time"]).isocalendar()[:2] == last_wk]
    assert lv["PWH"].price == max(b["high"] for b in pw)
    assert lv["PWL"].price == min(b["low"] for b in pw)
    # 线从本周第一根画起
    first_of_week = next(i for i, b in enumerate(bars) if date.fromisoformat(b["time"]).isocalendar()[:2] == wk)
    assert lv["PWH"].start_idx == first_of_week


def test_key_levels_depend_on_frequency():
    bars = _bars(_line(10, 30, 15, 40, 20, 35), start="2025-01-01")
    assert {k.code for k in algo.key_levels(bars, "weekly")} <= {"PMH", "PML"}
    m30 = []
    for d in range(1, 15):
        for hhmm in ("10:00", "10:30", "11:00"):
            p = 100 + d
            m30.append({"time": f"2025-01-{d:02d} {hhmm}", "open": p, "high": p + 1, "low": p - 1, "close": p, "volume": 1.0})
    codes = {k.code for k in algo.key_levels(m30, "30min")}
    assert {"PDH", "PDL"} <= codes


def test_analyze_handles_short_or_flat_input():
    assert algo.analyze([], swing_len=3).breaks == []
    flat = _bars([10.0] * 30)
    res = algo.analyze(flat, swing_len=3)
    assert res.breaks == [] and res.order_blocks == []


def test_fvg_threshold_is_twice_the_mean_body_of_all_earlier_candles():
    """阈值 = 2 × 第 0..i-1 根实体的均值（含中间那根自己）。中间实体 1.04% 刚好越过 1.01%（但不到除以 i-1 时的 1.063%）。"""
    bars = [{"time": f"2025-01-{d + 1:02d}", "open": 100.0, "high": 100.6, "low": 99.9, "close": 100.5, "volume": 1.0}
            for d in range(20)]                                               # 20 根实体 0.5%
    bars.append({"time": "2025-02-01", "open": 100.0, "high": 100.2, "low": 99.9, "close": 100.1, "volume": 1.0})    # 第一根，实体 0.1%
    mid_close = 100.1 * 1.0104
    bars.append({"time": "2025-02-02", "open": 100.1, "high": mid_close + 0.05, "low": 100.1, "close": mid_close, "volume": 1.0})
    bars.append({"time": "2025-02-03", "open": mid_close, "high": 102.0, "low": 100.5, "close": 101.5, "volume": 1.0})
    gaps = [g for g in algo.analyze(bars, swing_len=3).fvgs if g.idx == 21]
    assert gaps and (gaps[0].bottom, gaps[0].top) == (100.2, 100.5)
