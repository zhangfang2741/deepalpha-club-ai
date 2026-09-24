"""日志初始化：HTTP 客户端库不得在 INFO/DEBUG 级别打印完整请求 URL。

FMP 等数据源把 apikey 放在查询参数里，httpx/httpcore/urllib3 的请求日志会把它明文
写进控制台与日志文件（线上即 Railway 日志）。这些库只保留 WARNING 及以上。
"""
import logging

from app.core.logging import setup_logging


def test_http_client_loggers_are_quiet_after_setup():
    """初始化后 httpx / httpcore / urllib3 自身显式设为 WARNING（不依赖根 logger 级别）。"""
    setup_logging()
    for name in ("httpx", "httpcore", "urllib3"):
        assert logging.getLogger(name).level >= logging.WARNING, name
