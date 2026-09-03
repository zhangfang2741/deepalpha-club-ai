"""A 股标的代码归一化与市场推断。

内部统一使用 `<6位代码>.<SH|SZ|BJ>` 形式，如 `600519.SH` / `000001.SZ` / `430047.BJ`。

市场判定规则（按 6 位代码首位/前缀）：
- 沪市 SH：6 开头（主板 600/601/603/605、科创板 688）、9 开头（B 股）
- 深市 SZ：0 开头（主板/中小板 000/001/002/003）、3 开头（创业板 300/301）、2 开头（B 股）
- 北交所 BJ：4 开头（430/830…）、8 开头（新三板精选层→北交所 87/83/88）
"""

from __future__ import annotations

import re

SH = "SH"
SZ = "SZ"
BJ = "BJ"

_CODE_RE = re.compile(r"^\d{6}$")


class InvalidSymbolError(ValueError):
    """无法识别的 A 股代码。"""


def _infer_market(code: str) -> str:
    """按 6 位代码首位推断交易所后缀。"""
    head = code[0]
    if head in ("6", "9"):
        return SH
    if head in ("0", "2", "3"):
        return SZ
    if head in ("4", "8"):
        return BJ
    raise InvalidSymbolError(f"无法识别的 A 股代码：{code}")


def split_symbol(symbol: str) -> tuple[str, str]:
    """把任意写法的代码拆成 (6 位代码, 交易所后缀 SH/SZ/BJ)。

    接受形式：`600519`、`600519.SH`、`sh600519`、`SH600519`、`600519.XSHG`。
    后缀若显式给出则以其为准（映射到 SH/SZ/BJ）；否则按代码首位推断。
    """
    if not symbol:
        raise InvalidSymbolError("代码为空")
    s = symbol.strip().upper().replace(" ", "")

    suffix: str | None = None
    # 形如 600519.SH / 600519.XSHG
    if "." in s:
        code, _, raw_suffix = s.partition(".")
        suffix = _map_suffix(raw_suffix)
    # 形如 SH600519 / SZ000001
    elif s[:2] in (SH, SZ, BJ) and s[2:].isdigit():
        suffix = s[:2]
        code = s[2:]
    else:
        code = s

    if not _CODE_RE.match(code):
        raise InvalidSymbolError(f"代码应为 6 位数字：{symbol}")

    if suffix is None:
        suffix = _infer_market(code)
    return code, suffix


def _map_suffix(raw: str) -> str:
    """把各种后缀写法映射到 SH/SZ/BJ。"""
    raw = raw.upper()
    mapping = {
        "SH": SH, "XSHG": SH, "SS": SH,
        "SZ": SZ, "XSHE": SZ,
        "BJ": BJ, "BSE": BJ,
    }
    if raw not in mapping:
        raise InvalidSymbolError(f"无法识别的交易所后缀：{raw}")
    return mapping[raw]


def normalize_symbol(symbol: str) -> str:
    """归一化为内部标准形式 `<code>.<SH|SZ|BJ>`。"""
    code, suffix = split_symbol(symbol)
    return f"{code}.{suffix}"


def eastmoney_secid(symbol: str) -> str:
    """转成东方财富行情接口的 secid：`<市场号>.<代码>`。

    市场号：1=沪(SH)，0=深(SZ)，0=北交所(BJ，东方财富北交所走深市通道号 0)。
    """
    code, suffix = split_symbol(symbol)
    market = "1" if suffix == SH else "0"
    return f"{market}.{code}"


def akshare_code(symbol: str) -> str:
    """转成 akshare 常用的纯 6 位代码。"""
    code, _ = split_symbol(symbol)
    return code
