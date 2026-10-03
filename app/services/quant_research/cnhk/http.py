"""A 股 / 港股公开数据接口的礼貌访问层：进程级闸门（并发上限 + 最小请求间隔）+ 重试，不走 .env 代理。

东财数据中心 / F10 与经济通从 Railway 美国机房实测可达（东财行情 push2 不可达，这里不用）。
批量与用户实时请求共用同一个闸门：夜间批量再忙，单个站点的请求速率也不会超过上限。
"""

from __future__ import annotations

import asyncio
import time

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import logger

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


class SourceBusy(Exception):
    """数据源返回「服务器繁忙」等可重试的错误。"""


class _Gate:
    """并发上限 + 相邻请求最小间隔（同一站点共享）。"""

    def __init__(self, concurrency: int, min_interval: float):
        self._sem = asyncio.Semaphore(concurrency)
        self._lock = asyncio.Lock()
        self._min_interval = min_interval
        self._last = 0.0

    async def __aenter__(self) -> None:
        await self._sem.acquire()
        async with self._lock:
            wait = self._last + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    async def __aexit__(self, *_exc) -> None:
        self._sem.release()


_GATES: dict[tuple[str, int], _Gate] = {}
_LIMITS = {"eastmoney": (3, 0.25), "etnet": (2, 0.5)}


def _gate(site: str) -> _Gate:
    # asyncio 原语绑定事件循环：按「站点 + 当前循环」各建一个（测试 / 脚本里会多次 asyncio.run）
    key = (site, id(asyncio.get_running_loop()))
    g = _GATES.get(key)
    if g is None:
        g = _GATES[key] = _Gate(*_LIMITS[site])
    return g


def new_client(timeout: float = 20) -> httpx.AsyncClient:
    """数据源专用客户端：trust_env=False（.env 的代理是给境外 LLM API 用的）。"""
    return httpx.AsyncClient(timeout=timeout, trust_env=False, headers={"User-Agent": _UA}, follow_redirects=True)


async def get(client: httpx.AsyncClient, site: str, url: str, params: dict | None = None) -> httpx.Response:
    """经闸门的 GET；网络错误 / 5xx / 429 最多重试 3 次（指数退避）。"""
    async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8),
                                       retry=retry_if_exception_type((httpx.TransportError, SourceBusy)),
                                       reraise=True):
        with attempt:
            async with _gate(site):
                resp = await client.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("cnhk_source_retry", site=site, status=resp.status_code)
                raise SourceBusy(f"http {resp.status_code}")
            return resp
    raise AssertionError("unreachable")  # pragma: no cover
