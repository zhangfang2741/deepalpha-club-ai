"""共享 RSI(Wilder 平滑) 计算的单元测试。"""

import pytest

from app.services.rsi import rsi_series


def test_rsi_series_length_matches_input():
    closes = [float(i) for i in range(1, 20)]
    result = rsi_series(closes, period=14)
    assert len(result) == len(closes)


def test_rsi_series_none_before_warmup():
    closes = [float(i) for i in range(1, 20)]
    result = rsi_series(closes, period=14)
    for v in result[:14]:
        assert v is None
    assert result[14] is not None


def test_rsi_series_too_short_returns_all_none():
    closes = [1.0, 2.0, 3.0]
    result = rsi_series(closes, period=14)
    assert result == [None, None, None]


def test_rsi_is_100_when_all_gains_no_losses():
    closes = [float(i) for i in range(1, 20)]  # 单调上涨
    result = rsi_series(closes, period=14)
    assert result[14] == pytest.approx(100.0)


def test_rsi_is_0_when_all_losses_no_gains():
    closes = [float(20 - i) for i in range(19)]  # 单调下跌
    result = rsi_series(closes, period=14)
    assert result[14] == pytest.approx(0.0)


def test_rsi_is_50_when_gains_equal_losses():
    # 涨1跌1交替，14 期内涨跌幅完全对称
    closes = [10.0]
    for i in range(14):
        closes.append(closes[-1] + (1.0 if i % 2 == 0 else -1.0))
    result = rsi_series(closes, period=14)
    assert result[14] == pytest.approx(50.0)


def test_rsi_stays_within_bounds():
    closes = [10.0, 12.0, 9.0, 15.0, 8.0, 20.0, 5.0, 18.0, 11.0, 16.0,
              7.0, 19.0, 6.0, 17.0, 13.0, 14.0, 9.5, 18.5, 6.5]
    result = rsi_series(closes, period=14)
    for v in result:
        if v is not None:
            assert 0.0 <= v <= 100.0
