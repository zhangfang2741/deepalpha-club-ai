"""股票代码市场判别测试。

判错市场的后果是查错数据源，用户看到的是「未获取到 K 线数据」，
完全猜不到是代码格式的问题。
"""

import pytest

from app.utils.market import InvalidSymbolError, Market, detect_market, normalize


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600519", "600519"),
        ("SH600519", "600519"),
        ("sz000001", "000001"),
        ("600519.SS", "600519"),
        ("000001.SZ", "000001"),
    ],
)
def test_a_share(raw, expected):
    """A 股：6 位数字，前缀后缀都要能剥掉。"""
    market, clean = normalize(raw)
    assert market is Market.CN
    assert clean == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0700", "00700"),
        ("00700", "00700"),
        ("0700.HK", "00700"),
        ("HK0700", "00700"),
        ("9988", "09988"),
    ],
)
def test_hk_share(raw, expected):
    """港股：4–5 位数字统一补零到 5 位，akshare 接口要这个形态。"""
    market, clean = normalize(raw)
    assert market is Market.HK
    assert clean == expected


@pytest.mark.parametrize("raw", ["AAPL", "aapl", "NVDA", "BRK.B"])
def test_us_share(raw):
    """美股：字母代码，统一大写。"""
    market, clean = normalize(raw)
    assert market is Market.US
    assert clean == raw.upper()


@pytest.mark.parametrize("raw", ["", "   ", "123", "1234567", "!!!", "中文"])
def test_rejects_garbage(raw):
    with pytest.raises(InvalidSymbolError):
        normalize(raw)


def test_suffix_wins_over_digit_count():
    """显式后缀优先于位数判断：00700.HK 是 5 位，但不能被当成 A 股。"""
    assert detect_market("00700.HK") is Market.HK


def test_six_digits_is_a_share_not_hk():
    """6 位纯数字归 A 股，港股最多 5 位，两者不重叠。"""
    assert detect_market("600519") is Market.CN
