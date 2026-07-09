"""Celery worker liveness heartbeat.

worker 启动后由后台线程周期性写入一个带 TTL 的 Redis key；API 端读取该 key
即可可靠判断 worker 是否在消费队列。相比 celery control.ping 的广播探活，
这种「worker 主动写心跳」不受 broker 往返延迟影响，避免误报离线。
"""

from __future__ import annotations

import threading
import time

import redis
from celery.signals import worker_ready, worker_shutting_down

from app.core.config import settings
from app.core.logging import logger

HEARTBEAT_KEY = "supply_chain:worker:heartbeat"
HEARTBEAT_INTERVAL_SECONDS = 15
HEARTBEAT_TTL_SECONDS = 45

_stop = threading.Event()
_thread: threading.Thread | None = None
_read_client: redis.Redis | None = None


def _sync_redis() -> redis.Redis:
    """Build a sync Redis client from the Celery broker URL."""
    return redis.Redis.from_url(settings.CELERY_BROKER_URL)


def _get_read_client() -> redis.Redis:
    """Return a cached sync client for heartbeat reads (avoid per-call pools)."""
    global _read_client
    if _read_client is None:
        _read_client = _sync_redis()
    return _read_client


def _loop() -> None:
    client = _sync_redis()
    while not _stop.is_set():
        try:
            client.set(HEARTBEAT_KEY, str(time.time()), ex=HEARTBEAT_TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001 - 心跳失败不应中断 worker
            logger.warning("supply_chain_worker_heartbeat_failed", error=str(exc))
        _stop.wait(HEARTBEAT_INTERVAL_SECONDS)


@worker_ready.connect
def _start_heartbeat(**_: object) -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="sc-worker-heartbeat", daemon=True)
    _thread.start()
    logger.info("supply_chain_worker_heartbeat_started")


@worker_shutting_down.connect
def _stop_heartbeat(**_: object) -> None:
    _stop.set()


def read_worker_heartbeat() -> bool:
    """Return True if a fresh worker heartbeat exists in Redis."""
    try:
        return _get_read_client().get(HEARTBEAT_KEY) is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("supply_chain_worker_heartbeat_read_failed", error=str(exc))
        return False
