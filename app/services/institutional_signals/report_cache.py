"""详情页报告缓存的 key 与版本——供 API 端点与榜单扫描共用，确保二者写/读同一份缓存。

版本 = 影响输出的源码模块哈希：任一打分/状态/schema 改动即自动失效旧缓存，无需手动升版本。
用 importlib 惰性取模块源码，避免与 scan 的顶层循环依赖。
"""
import hashlib
import importlib
import inspect

# 影响榜单/详情输出的源码模块（顺序固定，改动顺序会改变版本串）
_SOURCE_MODULES = (
    "app.services.institutional_signals.dimensions",
    "app.services.institutional_signals.states",
    "app.services.institutional_signals.calculator",
    "app.services.institutional_signals.scan",
    "app.services.institutional_signals.constants",
    "app.services.institutional_signals.fetchers",
    "app.services.institutional_signals.deltas",
    "app.schemas.institutional_signals",
)


def report_cache_version() -> str:
    """由相关源码哈希算出缓存版本；读不到源码（纯 .pyc）时回退到模块名。"""
    h = hashlib.md5()
    for name in _SOURCE_MODULES:
        try:
            mod = importlib.import_module(name)
            h.update(inspect.getsource(mod).encode("utf-8"))
        except (OSError, TypeError, ImportError):
            h.update(name.encode("utf-8"))
    return h.hexdigest()[:10]


def report_cache_key(symbol: str, version: str) -> str:
    """单支标的详情报告的缓存 key。"""
    return f"institutional_signals:{symbol}:{version}"
