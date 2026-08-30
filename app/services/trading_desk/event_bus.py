"""交易台事件总线：Redis Stream 读写。

选 Stream 而非 Pub/Sub 的原因：
  - Stream ID 天然单调，直接充当 SSE 的 Last-Event-ID，断线重连即续读
  - 事件被持久化，刷新页面 / 多标签页可以接回同一个 run
  - Pub/Sub 的消息发出即丢，订阅晚一步就永久错过开头

用 XRANGE 轮询而非 XREAD BLOCK：redis-py 的阻塞读会占住连接池里的连接，
一个长跑的 run 配多个订阅者时容易把池吃干；轮询间隔 50ms 对人眼已足够。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.schemas.trading_desk import TradingDeskEvent

# 订阅端默认参数
_POLL_INTERVAL = 0.05
# 超过这个时长没有任何新事件就断开：防止 runner 崩溃后订阅者永久挂着
_IDLE_TIMEOUT = 300.0
_BATCH = 200


def stream_key(run_id: str) -> str:
    """事件流的 Redis key。"""
    return f"td:events:{run_id}"


def seq_key(run_id: str) -> str:
    """事件序号计数器的 Redis key。"""
    return f"td:seq:{run_id}"


def _decode(value: bytes | str) -> str:
    """连接池配置了 decode_responses=False，Stream ID 回来是 bytes。"""
    return value.decode() if isinstance(value, bytes) else str(value)


async def publish(redis: Redis, run_id: str, event: TradingDeskEvent) -> str:
    """写入一条事件，回填 seq，返回 Redis Stream ID。"""
    ttl = settings.TRADING_DESK_EVENT_TTL_SECONDS

    event.seq = await redis.incr(seq_key(run_id))
    await redis.expire(seq_key(run_id), ttl)

    key = stream_key(run_id)
    raw_id = await redis.xadd(key, {"e": event.model_dump_json()})  # type: ignore[misc]
    await redis.expire(key, ttl)

    return _decode(raw_id)


async def subscribe(
    redis: Redis,
    run_id: str,
    last_id: str | None = None,
    *,
    poll_interval: float = _POLL_INTERVAL,
    idle_timeout: float = _IDLE_TIMEOUT,
) -> AsyncIterator[tuple[str, TradingDeskEvent]]:
    """从 last_id 之后开始消费事件，直到终止事件或空闲超时。

    Args:
        redis: Redis 客户端。
        run_id: 运行 ID。
        last_id: 上次收到的 Stream ID（来自 SSE 的 Last-Event-ID）。
            None 表示从头重放。
        poll_interval: 无新事件时的轮询间隔。传 0 表示不等待，取完即返回。
        idle_timeout: 连续无新事件多久后放弃。

    Yields:
        tuple[str, TradingDeskEvent]: (stream_id, event)，stream_id 用于
            SSE 的 id 字段。
    """
    cursor = last_id or "0-0"
    idle = 0.0

    while True:
        # 用闭区间 + 跳过首条，而不是 Redis 6.2 才有的排他区间 "(id"：
        # 少一个对服务端版本的假设，本地替身也能忠实模拟同一套语义。
        entries = await redis.xrange(stream_key(run_id), min=cursor, max="+", count=_BATCH)  # type: ignore[misc]
        if entries and _decode(entries[0][0]) == cursor:
            entries = entries[1:]

        if not entries:
            if poll_interval <= 0 or idle >= idle_timeout:
                return
            await asyncio.sleep(poll_interval)
            idle += poll_interval
            continue

        idle = 0.0
        for entry_id, fields in entries:
            cursor = _decode(entry_id)
            raw = fields.get(b"e") or fields.get("e")
            if raw is None:
                logger.warning("trading_desk_event_missing_payload", run_id=run_id, entry_id=cursor)
                continue

            event = TradingDeskEvent.model_validate_json(raw)
            yield cursor, event

            if event.is_terminal():
                return
