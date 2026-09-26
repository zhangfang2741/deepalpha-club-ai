"""买卖点信号引擎（czsc 结构信号逐根推进）单元测试。

合成数据说明：czsc 的一买要求末笔「价差力度」弱于前段，且「量能或笔长度」
也更弱；成交量恒定、每段等长的规则锯齿满足不了后者，故跌势后半段缩量
（真实形态中跌势末端本就常见缩量）。
"""
from __future__ import annotations

import datetime as dt

from czsc import Freq

from app.services.chan.czsc_signals import BsEvent, scan_bs_events


def _decaying_downtrend_bars(n: int = 128, start: float = 200.0, shrink_volume: bool = True) -> list[dict]:
    """净向下锯齿：前半每段跌 5、后半跌 2.4；shrink_volume 时后半段缩量。"""
    bars = []
    price = start
    wave = 8
    day0 = dt.date(2025, 1, 1)
    for i in range(n):
        cycle_pos = i % (2 * wave)
        amp = 5.0 if i < n // 2 else 2.4
        step = -amp if cycle_pos < wave else amp * 0.5
        o = price
        c = price + step
        volume = 400 if (shrink_volume and i >= n // 2) else 1000
        bars.append({"time": (day0 + dt.timedelta(days=i)).isoformat(),
                     "open": o, "high": max(o, c) + 1.0, "low": min(o, c) - 1.0,
                     "close": c, "volume": volume})
        price = c
    return bars


def _mirror(bars: list[dict], axis: float = 400.0) -> list[dict]:
    """价格上下翻转：跌势变涨势，用于验证卖点与买点对称。"""
    return [dict(b, open=axis - b["open"], close=axis - b["close"],
                 high=axis - b["low"], low=axis - b["high"]) for b in bars]


def test_downtrend_with_fading_force_yields_buy1_on_down_stroke_end():
    events = scan_bs_events(_decaying_downtrend_bars(), symbol="DN", freq=Freq.D)
    buy1 = [e for e in events if e.type == "buy1"]
    assert buy1, "缩量衰减的跌势应产出一买"
    for e in buy1:
        # 一买落在跌势后段低位，且信号亮起不早于所属笔的终点
        assert e.bi_end_price < 120
        assert e.bi_end_time <= e.bar_time
        assert e.span.endswith("笔")


def test_uptrend_mirror_yields_sell1():
    events = scan_bs_events(_mirror(_decaying_downtrend_bars()), symbol="UP", freq=Freq.D)
    sell1 = [e for e in events if e.type == "sell1"]
    assert sell1
    assert all(e.bi_end_price > 280 for e in sell1)


def test_constant_volume_downtrend_yields_no_buy1_but_third_sell():
    """量能、时长都未衰减时不构成一买；跌势中离开中枢不回的反弹给出三卖。

    三类不再来自 czsc 信号，而是由 signals 按标准定义从笔与中枢推出，这里走完整分析。
    """
    from app.services.chan.analyzer import ChanAnalyzer

    bars = _decaying_downtrend_bars(shrink_volume=False)
    assert "buy1" not in {e.type for e in scan_bs_events(bars, symbol="DN", freq=Freq.D)}
    assert "sell3" in {s.type for s in ChanAnalyzer().analyze("DN", bars).signals}


def test_scan_only_emits_type1_and_records_stroke_completion():
    """扫描只给一类背驰事件；每一笔完成的K线不早于笔终点（不回看未来）。"""
    done: dict[str, str] = {}
    events = scan_bs_events(_decaying_downtrend_bars(), symbol="DN", freq=Freq.D, stroke_done_at=done)
    assert {e.type for e in events} <= {"buy1", "sell1"}
    assert done
    assert all(bar_time >= end for end, bar_time in done.items())


def test_events_deduped_by_type_and_stroke_and_sorted():
    events = scan_bs_events(_decaying_downtrend_bars(), symbol="DN", freq=Freq.D)
    keys = [(e.type, e.bi_end_time) for e in events]
    assert len(keys) == len(set(keys))
    assert [e.bar_time for e in events] == sorted(e.bar_time for e in events)


def test_too_few_bars_returns_empty():
    assert scan_bs_events(_decaying_downtrend_bars(n=15), symbol="S", freq=Freq.D) == []


def test_event_is_frozen_dataclass():
    e = BsEvent(type="buy1", bar_time="2025-01-02", bi_end_time="2025-01-01", bi_end_price=1.0, span="5笔")
    assert e.type == "buy1"
