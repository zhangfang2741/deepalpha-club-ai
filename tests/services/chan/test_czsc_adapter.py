"""czsc 适配层单元测试：bars(list[dict]) -> czsc.RawBar 的转换。"""
from __future__ import annotations

from czsc import Freq

from app.services.chan.czsc_adapter import bars_to_raw_bars, build_czsc


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
    for i in range(n):
        cycle_pos = i % (2 * wave)
        step = sign * (amp if cycle_pos < wave else -amp * down_ratio)
        o = price
        c = price + step
        h = max(o, c) + 1.0
        low_ = min(o, c) - 1.0
        price = c
        bars.append(_bar(f"2024-01-{i + 1:02d}" if i < 28 else f"2024-02-{i - 27:02d}", o, h, low_, c))
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
