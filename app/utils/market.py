"""股票代码的市场判别与归一化。

三个市场的代码形态天然可区分，不需要用户手动选：

- A 股：6 位数字，可带 SH/SZ 前缀或 .SS/.SZ 后缀（600519、SH600519、600519.SS）
- 港股：4~5 位数字，可带 HK 前缀或 .HK 后缀（0700、00700、HK0700、0700.HK）
- 美股：字母代码（AAPL、BRK.B）

判别顺序是「先 A 股再港股最后美股」：A 股的 6 位与港股的 4~5 位不重叠，
而美股是字母，三者互不冲突。歧义只可能出现在带后缀的写法上，所以后缀优先于
位数判断。
"""
from __future__ import annotations

import re
from enum import Enum


class Market(str, Enum):
    """标的所属市场。"""

    US = "us"
    CN = "cn"
    HK = "hk"


class InvalidSymbolError(ValueError):
    """代码格式无法识别。"""


_CN_PREFIX = re.compile(r"^(SH|SZ)", re.IGNORECASE)
_CN_SUFFIX = re.compile(r"\.(SS|SZ|SH)$", re.IGNORECASE)
_HK_PREFIX = re.compile(r"^HK", re.IGNORECASE)
_HK_SUFFIX = re.compile(r"\.HK$", re.IGNORECASE)
_US_SYMBOL = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


def detect_market(symbol: str) -> Market:
    """判别代码属于哪个市场。

    Raises:
        InvalidSymbolError: 代码为空或格式无法识别。
    """
    raw = (symbol or "").strip()
    if not raw:
        raise InvalidSymbolError("请输入股票代码")

    upper = raw.upper()

    # 显式后缀/前缀优先：写了 .HK 就按港股处理，不再看位数
    if _HK_SUFFIX.search(upper) or _HK_PREFIX.match(upper):
        return Market.HK
    if _CN_SUFFIX.search(upper) or _CN_PREFIX.match(upper):
        return Market.CN

    digits = re.sub(r"\D", "", upper)
    if digits == upper:  # 纯数字
        if len(digits) == 6:
            return Market.CN
        if 4 <= len(digits) <= 5:
            return Market.HK
        raise InvalidSymbolError("代码位数不对：A 股 6 位、港股 4–5 位")

    if _US_SYMBOL.match(upper):
        return Market.US

    raise InvalidSymbolError("无法识别的股票代码")


def normalize(symbol: str) -> tuple[Market, str]:
    """判别市场并归一化成该市场数据源要的形态。

    Returns:
        (市场, 归一化代码)。A 股是 6 位裸号，港股是 5 位补零裸号，美股是大写字母。

    Raises:
        InvalidSymbolError: 格式无法识别。
    """
    market = detect_market(symbol)
    upper = (symbol or "").strip().upper()

    if market is Market.CN:
        clean = _CN_SUFFIX.sub("", _CN_PREFIX.sub("", upper))
        if not re.fullmatch(r"\d{6}", clean):
            raise InvalidSymbolError("A 股代码应为 6 位数字")
        return market, clean

    if market is Market.HK:
        clean = _HK_SUFFIX.sub("", _HK_PREFIX.sub("", upper))
        if not re.fullmatch(r"\d{4,5}", clean):
            raise InvalidSymbolError("港股代码应为 4–5 位数字")
        # akshare 的港股接口要 5 位，0700 要补成 00700
        return market, clean.zfill(5)

    return market, upper
