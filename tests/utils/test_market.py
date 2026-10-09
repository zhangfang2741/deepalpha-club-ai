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


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AAPL", "AAPL"),
        ("600519", "600519.SS"),
        ("000001", "000001.SZ"),
        ("300750", "300750.SZ"),
        ("688981", "688981.SS"),     # 科创板 6 开头归沪
        ("510300", "510300.SS"),     # 沪市 ETF（5 开头）归沪，此前被误判成深
        ("588000", "588000.SS"),     # 科创50 ETF
        ("510050", "510050.SS"),     # 上证50 ETF
        ("159915", "159915.SZ"),     # 深市 ETF（1 开头）归深
        ("0700", "0700.HK"),
        ("00700", "0700.HK"),
        ("00700.HK", "0700.HK"),
        ("09988", "9988.HK"),
    ],
)
def test_fmp_symbol(raw, expected):
    """FMP 的代码形态：港股 4 位不补零，A 股按沪深加不同后缀。

    港股补成 5 位在 FMP 上查不到——search-symbol 返回的是 0700.HK。
    """
    from app.utils.market import fmp_symbol

    assert fmp_symbol(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600519", "1.600519"),      # 沪市
        ("000001", "0.000001"),      # 深市
        ("300750", "0.300750"),      # 创业板归深市
        ("510300", "1.510300"),      # 沪市 ETF（5 开头）归沪
        ("159915", "0.159915"),      # 深市 ETF（1 开头）归深
        ("0700", "116.00700"),       # 港股补零到 5 位
        ("03887", "116.03887"),
    ],
)
def test_eastmoney_secid(raw, expected):
    """东方财富的 secid：1=沪、0=深、116=港，港股要 5 位。"""
    from app.utils.market import eastmoney_secid

    assert eastmoney_secid(raw) == expected


def test_eastmoney_rejects_us():
    """美股不该走这条路，明确报错而不是拼出一个查不到的 secid。"""
    from app.utils.market import InvalidSymbolError, eastmoney_secid

    with pytest.raises(InvalidSymbolError):
        eastmoney_secid("AAPL")


# ───────── 回归：SH / SZ / HK 开头的美股代码不能被当成 A 股 / 港股前缀 ─────────
# 前缀只在后面紧跟数字时才算市场前缀（SH600519、SZ000001、HK0700）；SHOP、SHW、SHEL、SHY 这些是美股。

@pytest.mark.parametrize("symbol", ["SHOP", "SHW", "SHEL", "SHY", "SHAK", "SHLS", "SZ", "SH", "HKD", "HKXX", "shop"])
def test_us_tickers_starting_with_market_prefix_letters_are_us(symbol):
    from app.utils.market import Market, detect_market, normalize

    assert detect_market(symbol) is Market.US
    market, clean = normalize(symbol)
    assert market is Market.US and clean == symbol.upper()


@pytest.mark.parametrize("symbol,market,clean", [
    ("SH600519", "cn", "600519"),
    ("sz000001", "cn", "000001"),
    ("600519.SS", "cn", "600519"),
    ("HK0700", "hk", "00700"),
    ("hk00700", "hk", "00700"),
    ("0700.HK", "hk", "00700"),
])
def test_explicit_market_prefix_with_digits_still_works(symbol, market, clean):
    from app.utils.market import normalize

    m, c = normalize(symbol)
    assert (m.value, c) == (market, clean)


def test_fmp_symbol_for_us_tickers_with_sh_prefix():
    from app.utils.market import fmp_symbol

    assert fmp_symbol("SHOP") == "SHOP"
    assert fmp_symbol("SHW") == "SHW"
