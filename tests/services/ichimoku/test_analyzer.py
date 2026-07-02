"""一目均衡表分析引擎单元测试。"""
from __future__ import annotations

from datetime import date, timedelta

from app.services.ichimoku.analyzer import IchimokuAnalyzer
from app.services.ichimoku.indicators import (
    base_line,
    conversion_line,
    leading_span_a,
    leading_span_b,
)


def _bar(t: str, o: float, h: float, low: float, c: float, v: float = 1000) -> dict:
    return {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": v}


def _series(prices: list[float]) -> list[dict]:
    """按收盘价序列构造 K 线（工作日递增，high/low 围绕收盘价 ±1）。"""
    bars: list[dict] = []
    cur = date(2024, 1, 1)
    for i, p in enumerate(prices):
        # 跳过周末
        while cur.weekday() >= 5:
            cur = cur + timedelta(days=1)
        o = prices[i - 1] if i > 0 else p
        bars.append(_bar(cur.isoformat(), o, p + 1.0, p - 1.0, p))
        cur = cur + timedelta(days=1)
    return bars


def test_conversion_and_base_line_midpoint():
    """转换线/基准线应为窗口内 (最高价+最低价)/2。"""
    prices = [float(x) for x in range(1, 31)]  # 单调上升
    bars = _series(prices)

    conv = conversion_line(bars, period=9)
    base = base_line(bars, period=26)

    # 不足周期处为 None
    assert conv[7] is None
    assert conv[8] is not None
    assert base[24] is None
    assert base[25] is not None

    # 第 9 根（下标 8）：近 9 根 high 最大 = price[8]+1=9+1? price 从1..，下标8=9，high=10
    # low 最小 = price[0]-1 = 1-1 = 0 -> 中值 = (10+0)/2 = 5
    assert conv[8] == (10.0 + 0.0) / 2.0


def test_leading_span_a_is_average_of_conv_base():
    prices = [float(x) for x in range(1, 40)]
    bars = _series(prices)
    conv = conversion_line(bars, 9)
    base = base_line(bars, 26)
    span_a = leading_span_a(conv, base)
    span_b = leading_span_b(bars, 52)

    # span_a 在 conv/base 都有值处 = (conv+base)/2
    i = 30
    assert span_a[i] == (conv[i] + base[i]) / 2.0
    # 52 周期不足 -> span_b 全 None
    assert all(v is None for v in span_b)


def test_analyze_insufficient_data():
    bars = _series([float(x) for x in range(1, 10)])  # 只有 9 根
    result = IchimokuAnalyzer().analyze("TEST", bars)
    assert result.bars_count == 9
    assert "不足" in result.summary
    assert result.state is None


def test_analyze_uptrend_is_bullish():
    """持续上涨行情：价格应在云上，建议偏多。"""
    prices = [float(x) for x in range(1, 90)]  # 长期单边上涨
    bars = _series(prices)
    result = IchimokuAnalyzer().analyze("UP", bars)

    assert result.state is not None
    assert result.state.price_vs_cloud == "above"
    assert result.recommendation is not None
    assert result.recommendation.bias == "bullish"
    # 先行带前移后，其时间应超出最后一根 K 线（存在未来时间点）
    last_candle_time = result.candles[-1].time
    assert any(p.time > last_candle_time for p in result.senkou_a)


def test_analyze_downtrend_is_bearish():
    prices = [float(x) for x in range(90, 1, -1)]  # 长期单边下跌
    bars = _series(prices)
    result = IchimokuAnalyzer().analyze("DOWN", bars)

    assert result.state is not None
    assert result.state.price_vs_cloud == "below"
    assert result.recommendation is not None
    assert result.recommendation.bias == "bearish"


def test_chikou_is_shifted_back():
    """迟行线点数应为 N - displacement，且时间落在历史区间内。"""
    prices = [float(x) for x in range(1, 90)]
    bars = _series(prices)
    result = IchimokuAnalyzer().analyze("CHIKOU", bars)

    assert len(result.chikou) == len(bars) - 26
    # 迟行线最后一个点的时间应早于最后一根 K 线
    assert result.chikou[-1].time < result.candles[-1].time


def test_future_cloud_color_uses_latest_span_not_current_cloud():
    """前方云颜色应由最新一根算得（未来 kumo），可与当前所处云颜色不同。

    构造：长期下跌后近期反转拉升。反转后最新先行带 A 上穿 B → 前方云转阳，
    而价格当前所处的滞后云（26 根前算得）仍可能是阴云。
    """
    down = [float(x) for x in range(200, 90, -1)]   # 长期下跌
    up = [float(x) for x in range(90, 170)]          # 近期强反转
    bars = _series(down + up)
    r = IchimokuAnalyzer().analyze("REV", bars)
    assert r.state is not None
    # 反转后未来云应转阳
    assert r.state.future_cloud_color == "bullish"
    # 前方云颜色是独立字段，不等同于当前所处云字段的取值来源
    assert hasattr(r.state, "future_cloud_color")


def test_na_cloud_recommendation_wording():
    """K 线在 [27, 78) 之间时无当前云，建议话术应说“数据不足”而非“云层之中”。"""
    prices = [float(x) for x in range(1, 41)]  # 40 根：够算基准线，但不足以形成当前云
    bars = _series(prices)
    r = IchimokuAnalyzer().analyze("NA", bars)
    assert r.state is not None
    assert r.state.price_vs_cloud == "na"
    assert r.recommendation is not None
    joined = "".join(r.recommendation.reasons)
    assert "数据不足" in joined
    assert "云层之中" not in joined


def test_tk_cross_signal_generated():
    """构造先跌后涨行情，应至少出现一次 TK 金叉。"""
    down = [float(x) for x in range(90, 40, -1)]
    up = [float(x) for x in range(40, 90)]
    bars = _series(down + up)
    result = IchimokuAnalyzer().analyze("CROSS", bars)

    assert any(s.type == "tk_golden" for s in result.signals)
    buy_types = {"tk_golden", "kumo_up", "chikou_bull"}
    for s in result.signals:
        assert s.strength in ("strong", "medium", "weak")
        assert s.is_buy == (s.type in buy_types)


def test_chikou_cross_signal_generated():
    """先跌后涨：迟行线（当期收盘）应上穿 26 期前价格，产生 chikou_bull。"""
    down = [float(x) for x in range(120, 60, -1)]
    up = [float(x) for x in range(60, 130)]
    bars = _series(down + up)
    result = IchimokuAnalyzer().analyze("CHK", bars)

    chikou = [s for s in result.signals if s.type in ("chikou_bull", "chikou_bear")]
    assert any(s.type == "chikou_bull" for s in chikou)
    for s in chikou:
        assert s.is_buy == (s.type == "chikou_bull")
        assert str(26) in s.description or "迟行线" in s.description


def test_displacement_shifts_projection_length():
    """平移周期改为 25（TradingView 约定）应改变先行带/迟行线的平移量。"""
    prices = [float(x) for x in range(1, 100)]
    bars = _series(prices)
    r26 = IchimokuAnalyzer(displacement=26).analyze("D26", bars)
    r25 = IchimokuAnalyzer(displacement=25).analyze("D25", bars)

    # 迟行线点数 = N - displacement：25 应比 26 多 1 个点
    assert len(r25.chikou) == len(r26.chikou) + 1
    # 先行带前移 25 期，未来最后时间应早于前移 26 期
    assert r25.senkou_a[-1].time < r26.senkou_a[-1].time
