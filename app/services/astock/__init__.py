"""A 股数据源服务：行情 K 线、实时快照、基本面、标的搜索。

- K 线：直连东方财富行情接口（前复权），与 akshare 的 A 股接口同源但更稳、不走代理。
- 快照 / 基本面 / 搜索：akshare。

所有外部调用为纯函数（不碰 DB / Redis），DB 缓存由上层 API 编排。
"""

from app.services.astock.symbols import (
    eastmoney_secid,
    normalize_symbol,
    split_symbol,
)

__all__ = [
    "eastmoney_secid",
    "normalize_symbol",
    "split_symbol",
]
