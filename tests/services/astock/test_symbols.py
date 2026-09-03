"""A 股代码归一化与市场推断测试。"""

import pytest

from app.services.astock.symbols import (
    InvalidSymbolError,
    akshare_code,
    eastmoney_secid,
    normalize_symbol,
    split_symbol,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600519", "600519.SH"),
        ("600519.SH", "600519.SH"),
        ("sh600519", "600519.SH"),
        ("688981", "688981.SH"),
        ("000001", "000001.SZ"),
        ("300750.XSHE", "300750.SZ"),
        ("SZ000001", "000001.SZ"),
        ("430047", "430047.BJ"),
        ("830799", "830799.BJ"),
    ],
)
def test_normalize_symbol(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("bad", ["", "60051", "6005190", "ABCDEF", "600519.XX"])
def test_invalid_symbol(bad):
    with pytest.raises(InvalidSymbolError):
        split_symbol(bad)


def test_eastmoney_secid_market_prefix():
    # 沪市 -> 1，深市 -> 0，北交所 -> 0
    assert eastmoney_secid("600519") == "1.600519"
    assert eastmoney_secid("000001") == "0.000001"
    assert eastmoney_secid("430047") == "0.430047"


def test_akshare_code_strips_suffix():
    assert akshare_code("600519.SH") == "600519"
    assert akshare_code("sz000001") == "000001"


def test_explicit_suffix_overrides_inference():
    # 显式后缀以其为准（即便与首位推断不同也不报错）
    code, suffix = split_symbol("600519.SZ")
    assert (code, suffix) == ("600519", "SZ")
