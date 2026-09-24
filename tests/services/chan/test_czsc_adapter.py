"""czsc 适配层单元测试：bars(list[dict]) -> czsc.RawBar 的转换。"""
from __future__ import annotations

import datetime as dt

from czsc import Freq

from app.services.chan.czsc_adapter import bars_to_raw_bars, build_czsc, extract_structures


def _bar(time: str, o: float, h: float, low: float, c: float, v: float = 1000.0) -> dict:
    return {"time": time, "open": o, "high": h, "low": low, "close": c, "volume": v}


def test_bars_to_raw_bars_preserves_ohlcv_and_order():
    bars = [
        _bar("2024-01-01", 10, 12, 9, 11, 500),
        _bar("2024-01-02", 11, 13, 10, 12.5, 600),
    ]
    raw_bars = bars_to_raw_bars(bars, symbol="TEST", freq=Freq.D)

    assert len(raw_bars) == 2
    assert raw_bars[0].symbol == "TEST"
    assert raw_bars[0].open == 10
    assert raw_bars[0].high == 12
    assert raw_bars[0].low == 9
    assert raw_bars[0].close == 11
    assert raw_bars[0].vol == 500
    assert raw_bars[0].id == 0
    assert raw_bars[1].id == 1


def test_bars_to_raw_bars_dt_is_chronologically_ordered():
    bars = [
        _bar("2024-01-01", 10, 12, 9, 11),
        _bar("2024-01-02", 11, 13, 10, 12.5),
    ]
    raw_bars = bars_to_raw_bars(bars, symbol="TEST", freq=Freq.D)

    assert raw_bars[0].dt < raw_bars[1].dt


def test_bars_to_raw_bars_empty_input_returns_empty_list():
    assert bars_to_raw_bars([], symbol="TEST", freq=Freq.D) == []


def _trending_bars(n: int, start_price: float, up: bool) -> list[dict]:
    """构造一段大幅锯齿波动（每 8 根一个上下周期，净向上），用于验证 CZSC 能识别出笔。

    注：czsc 的分型->笔确认逻辑比朴素想象中严格（见
    docs/superpowers/specs/2026-09-23-czsc-spike-findings.md 的 spike 结论）；
    小振幅、逐根交替的合成数据无法通过其确认门槛，实测需要足够振幅的多根一致
    走势（此处每段 8 根、上涨步长 5、回撤步长 2.5）才能稳定形成 >=1 笔。
    """
    bars = []
    price = start_price
    wave = 8
    amp = 5.0
    down_ratio = 0.5
    sign = 1.0 if up else -1.0
    day0 = dt.date(2024, 1, 1)
    for i in range(n):
        cycle_pos = i % (2 * wave)
        step = sign * (amp if cycle_pos < wave else -amp * down_ratio)
        o = price
        c = price + step
        h = max(o, c) + 1.0
        low_ = min(o, c) - 1.0
        price = c
        bars.append(_bar((day0 + dt.timedelta(days=i)).isoformat(), o, h, low_, c))
    return bars


def test_build_czsc_returns_object_with_structure_lists():
    bars = _trending_bars(40, start_price=100.0, up=True)
    c = build_czsc(bars, symbol="TEST", freq=Freq.D)

    assert c.symbol == "TEST"
    assert isinstance(c.fx_list, list)
    assert isinstance(c.bi_list, list)
    assert isinstance(c.zs_list, list)
    # 40 根波动 K 线足够形成至少一笔
    assert len(c.bi_list) >= 1


def test_extract_structures_maps_to_existing_dataclasses():
    bars = _trending_bars(80, start_price=100.0, up=True)
    c = build_czsc(bars, symbol="TEST", freq=Freq.D)
    structures = extract_structures(c, bars)

    times = {b["time"] for b in bars}
    # 分型
    for f in structures.fractals:
        assert f.type in ("top", "bottom")
        assert f.price == (f.candle.high if f.type == "top" else f.candle.low)
        assert f.left.idx + 1 == f.candle.idx == f.right.idx - 1
        assert f.time in times
    # 笔：首尾相连 + 方向交替
    for a, b in zip(structures.strokes, structures.strokes[1:], strict=False):
        assert a.end.time == b.start.time
        assert a.direction != b.direction
    for s in structures.strokes:
        assert s.start_time in times and s.end_time in times
        if s.direction == "up":
            assert s.start.type == "bottom" and s.end.type == "top"
            assert s.end_price > s.start_price
        else:
            assert s.start.type == "top" and s.end.type == "bottom"
            assert s.end_price < s.start_price
    # 笔级中枢
    for p in structures.stroke_pivots:
        assert p.zg > p.zd
        assert p.level == "stroke"
        assert all(any(el is s for s in structures.strokes) for el in p.elements)
    # 合并K线
    mcs = structures.merged_candles
    assert [mc.idx for mc in mcs] == list(range(len(mcs)))
    for a, b in zip(mcs, mcs[1:], strict=False):
        assert not (a.high >= b.high and a.low <= b.low)
        assert not (b.high >= a.high and b.low <= a.low)
        assert a.time < b.time
        assert a.raw_start <= a.raw_end


def _staircase_bars(n: int = 96, up_amp: float = 5.0, dn_amp: float = 1.0, wave: int = 8) -> list[dict]:
    """强势阶梯上涨：每段涨 up_amp、回调 dn_amp，回调低点始终高于前面的区间。"""
    bars = []
    price = 100.0
    day0 = dt.date(2025, 1, 1)
    for i in range(n):
        step = up_amp if (i % (2 * wave)) < wave else -dn_amp
        o, c = price, price + step
        bars.append(_bar((day0 + dt.timedelta(days=i)).isoformat(), o, max(o, c) + 0.5, min(o, c) - 0.5, c))
        price = c
    return bars


def test_extract_structures_drops_groups_with_fewer_than_three_strokes():
    """中枢至少 3 笔重叠：czsc 的 zs_list 只是把笔分组，1~2 笔的组也会返回，需丢弃。"""
    bars = _staircase_bars()
    c = build_czsc(bars, symbol="STAIR", freq=Freq.D)
    assert any(len(z.bis) < 3 for z in c.zs_list), "前提：czsc 原始分组里有不足 3 笔的组"
    structures = extract_structures(c, bars)
    assert all(len(p.elements) >= 3 for p in structures.stroke_pivots)
    assert structures.stroke_pivots == []


def _intraday_bars(days: int = 12, per_day: int = 8, start_price: float = 100.0) -> list[dict]:
    """30 分钟合成数据：每天 per_day 根，时间 YYYY-MM-DD HH:MM；大振幅锯齿以便成笔。"""
    bars = []
    price = start_price
    day0 = dt.date(2025, 3, 3)
    i = 0
    for d in range(days):
        day = day0 + dt.timedelta(days=d)
        for k in range(per_day):
            hh, mm = divmod(9 * 60 + 30 + 30 * k, 60)
            step = 5.0 if (i % 16) < 8 else -2.5
            o, c = price, price + step
            bars.append(_bar(f"{day.isoformat()} {hh:02d}:{mm:02d}", o, max(o, c) + 1.0, min(o, c) - 1.0, c))
            price = c
            i += 1
    return bars


def test_intraday_times_keep_minutes_and_do_not_collide():
    """30 分钟级别：结构时间保留到分钟，同一天多根合并K线时间互不相同。"""
    bars = _intraday_bars()
    c = build_czsc(bars, symbol="T", freq=Freq.F30)
    s = extract_structures(c, bars)
    times = {b["time"] for b in bars}
    assert s.strokes, "合成数据应能成笔"
    for st in s.strokes:
        assert st.start_time in times and st.end_time in times
        assert len(st.end_time) == 16  # YYYY-MM-DD HH:MM
    mc_times = [m.time for m in s.merged_candles]
    assert len(mc_times) == len(set(mc_times))


def test_daily_times_stay_date_only():
    bars = _trending_bars(40, start_price=100.0, up=True)
    s = extract_structures(build_czsc(bars, symbol="T", freq=Freq.D), bars)
    assert all(len(st.end_time) == 10 for st in s.strokes)


def test_analyzer_accepts_30min_freq():
    """以 30 分钟级别分析：结构与买卖点时间都保留到分钟。"""
    from app.services.chan.analyzer import ChanAnalyzer
    bars = _intraday_bars(days=16)
    r = ChanAnalyzer().analyze("T", bars, freq="30min")
    assert r.strokes
    assert all(len(st.end_time) == 16 for st in r.strokes)
    assert all(len(sig.time) == 16 for sig in r.signals)


def test_strokes_carry_czsc_force_values():
    """笔带上 czsc 自带的力度：价差 power_price、量能 power_volume、时长 length（去包含K线根数）。"""
    bars = _trending_bars(80, start_price=100.0, up=True)
    c = build_czsc(bars, symbol="T", freq=Freq.D)
    s = extract_structures(c, bars)
    assert len(s.strokes) == len(c.bi_list)
    for st, bi in zip(s.strokes, c.bi_list, strict=True):
        assert st.power_price == float(bi.power_price)
        assert st.power_volume == float(bi.power_volume)
        assert st.length == int(bi.length)
        assert st.power_price == round(abs(st.end_price - st.start_price), 2)


def test_segment_force_aggregates_its_strokes():
    from app.services.chan.segment import Segment
    from app.services.chan.stroke import Stroke

    bars = _trending_bars(80, start_price=100.0, up=True)
    strokes = extract_structures(build_czsc(bars, symbol="T", freq=Freq.D), bars).strokes[:3]
    seg = Segment(direction=strokes[0].direction, strokes=list(strokes))
    assert seg.power_price == round(abs(seg.end_price - seg.start_price), 2)
    assert seg.power_volume == sum(x.power_volume for x in strokes)
    assert seg.length == sum(x.length for x in strokes)
    assert isinstance(strokes[0], Stroke)
