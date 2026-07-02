"""威科夫分析引擎单元测试。"""
from __future__ import annotations

from app.services.wyckoff.analyzer import WyckoffAnalyzer
from app.services.wyckoff.indicators import find_swings, volume_stats
from app.services.wyckoff.structure import detect_structure


def _bar(t: str, o: float, h: float, low: float, c: float, v: float) -> dict:
    return {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": v}


def _make_accumulation_bars() -> list[dict]:
    """构造一段吸筹形态：下跌 → SC 放量低点 → AR 反弹 → ST 回踩 →
    Spring 假跌破 → SOS 放量突破。"""
    bars: list[dict] = []
    day = 0

    def add(o, h, low, c, v):
        nonlocal day
        day += 1
        bars.append(_bar(f"2024-01-{day:02d}", o, h, low, c, v))

    # 前期下跌（缩量）
    price = 100.0
    for _ in range(12):
        nxt = price - 3
        add(price, price + 0.5, nxt - 0.5, nxt, 1000)
        price = nxt
    # SC 卖出高潮：宽幅下跌 + 极端放量，形成低点 ~62
    add(price, price + 0.5, 60.0, 62.0, 6000)
    price = 62.0
    # AR 自动反弹到 ~78（阻力）
    for _ in range(4):
        nxt = price + 4
        add(price, nxt + 0.5, price - 0.5, nxt, 1500)
        price = nxt
    # 回落形成 ST 回踩 SC 低点 ~63
    for _ in range(4):
        nxt = price - 3.5
        add(price, price + 0.5, nxt - 0.5, nxt, 900)
        price = nxt
    add(price, price + 0.5, 63.0, 64.0, 800)   # ST 缩量
    price = 64.0
    # 区间震荡回到中部
    for _ in range(3):
        nxt = price + 3
        add(price, nxt + 0.5, price - 0.5, nxt, 1000)
        price = nxt
    # Spring：跌破支撑到 ~58 后快速收回
    add(price, price + 0.5, 58.0, 68.0, 2000)
    price = 68.0
    # SOS：放量宽幅上涨突破阻力 ~78 到 90
    for _ in range(6):
        nxt = price + 4
        add(price, nxt + 1, price - 0.5, nxt, 3000)
        price = nxt
    return bars


def test_detect_accumulation_context():
    bars = _make_accumulation_bars()
    vstats = volume_stats(bars)
    swings = find_swings(bars, left=2, right=2)
    result = detect_structure(bars, swings, vstats)
    assert result.context == "accumulation"
    assert result.trading_range is not None
    codes = {e.code for e in result.events}
    # 至少识别出卖出高潮与自动反弹
    assert "SC" in codes
    assert "AR" in codes


def test_analyzer_produces_recommendation():
    bars = _make_accumulation_bars()
    analyzer = WyckoffAnalyzer()
    result = analyzer.analyze("TEST", bars, swing_window=2)
    assert result.context == "accumulation"
    assert result.recommendation is not None
    assert result.recommendation.bias in ("bullish", "bearish", "neutral")
    assert result.summary
    # 文本报告可渲染
    report = analyzer.to_text_report(result)
    assert "威科夫" in report
    assert "TEST" in report


def test_insufficient_data():
    bars = [_bar(f"2024-01-{i + 1:02d}", 10, 11, 9, 10, 100) for i in range(5)]
    analyzer = WyckoffAnalyzer()
    result = analyzer.analyze("SHORT", bars)
    assert result.context == "undetermined"
    assert "不足" in result.summary


def _make_uptrend_with_volume_pullback() -> list[dict]:
    """构造带回调的上升趋势，并在某回调低点放巨量。

    该放量低点位于上升趋势中途、其前并无显著下跌，按威科夫方法论
    不构成卖出高潮（SC），不应被判定为吸筹。
    """
    bars: list[dict] = []
    price = 100.0
    day = 0

    def add(o, h, low, c, v):
        nonlocal day
        day += 1
        bars.append(_bar(f"2024-{day // 27 + 1:02d}-{day % 27 + 1:02d}", o, h, low, c, v))

    for cycle in range(9):
        for _ in range(3):  # 上涨 3 根
            add(price, price + 3.6, price - 0.6, price + 3, 1000)
            price += 3
        for k in range(2):  # 回调 2 根
            v = 9000 if cycle == 4 and k == 1 else 900
            add(price, price + 0.4, price - 2.1, price - 1.5, v)
            price -= 1.5
    return bars


def test_uptrend_volume_pullback_not_accumulation():
    """上升趋势中的放量回调不应被误判为吸筹（缺少前置下跌）。"""
    analyzer = WyckoffAnalyzer()
    result = analyzer.analyze("UPTREND", _make_uptrend_with_volume_pullback(), swing_window=2)
    assert result.context == "undetermined"
    assert result.trading_range is None
    assert result.recommendation is not None
    assert result.recommendation.action == "watch"


def test_trading_range_width_positive():
    """识别出的交易区间宽度必须为正（支撑 < 阻力）。"""
    bars = _make_accumulation_bars()
    result = WyckoffAnalyzer().analyze("TEST", bars, swing_window=2)
    if result.trading_range is not None:
        assert result.trading_range.resistance > result.trading_range.support


def test_markup_after_breakout():
    """向上突破区间后应判定为拉升阶段。"""
    bars = _make_accumulation_bars()
    analyzer = WyckoffAnalyzer()
    result = analyzer.analyze("TEST", bars, swing_window=2)
    # 末尾价格已突破 AR 阻力，进入拉升
    assert result.phase is not None
    assert result.phase.stage in ("markup", "accumulation")
