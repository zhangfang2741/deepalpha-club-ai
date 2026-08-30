"""交易台控制位的 Redis 操作测试。用只实现所需命令的内存替身。"""

from __future__ import annotations

from typing import Any

import pytest

from app.cache import trading_desk_cache as tdc


class FakeRedis:
    """只实现本模块用到的命令的内存替身。"""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[bytes, bytes]] = {}
        self.lists: dict[str, list[bytes]] = {}
        self.expires: dict[str, int] = {}

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        bucket = self.hashes.setdefault(key, {})
        for k, v in mapping.items():
            bucket[k.encode()] = str(v).encode()
        return len(mapping)

    async def hget(self, key: str, field: str) -> bytes | None:
        return self.hashes.get(key, {}).get(field.encode())

    async def rpush(self, key: str, *values: str) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket.extend(v.encode() for v in values)
        return len(bucket)

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        bucket = self.lists.get(key, [])
        return bucket[start:] if end == -1 else bucket[start : end + 1]

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.hashes.pop(key, None) is not None)
            removed += int(self.lists.pop(key, None) is not None)
        return removed

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


async def test_new_run_is_neither_paused_nor_cancelled(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")

    assert await tdc.is_paused(redis, "r1") is False
    assert await tdc.is_cancelled(redis, "r1") is False


async def test_pause_and_resume_round_trip(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")

    await tdc.set_paused(redis, "r1", True)
    assert await tdc.is_paused(redis, "r1") is True

    await tdc.set_paused(redis, "r1", False)
    assert await tdc.is_paused(redis, "r1") is False


async def test_cancel_is_sticky(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")
    await tdc.set_cancelled(redis, "r1")

    assert await tdc.is_cancelled(redis, "r1") is True


async def test_drain_notes_returns_and_clears(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")
    await tdc.push_note(redis, "r1", "第一条")
    await tdc.push_note(redis, "r1", "第二条")

    assert await tdc.drain_notes(redis, "r1") == ["第一条", "第二条"]
    assert await tdc.drain_notes(redis, "r1") == []


async def test_control_keys_carry_ttl(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")
    await tdc.push_note(redis, "r1", "x")

    assert redis.expires[tdc.control_key("r1")] > 0
    assert redis.expires[tdc.notes_key("r1")] > 0


async def test_clear_control_removes_both_keys(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")
    await tdc.push_note(redis, "r1", "x")

    await tdc.clear_control(redis, "r1")

    assert tdc.control_key("r1") not in redis.hashes
    assert tdc.notes_key("r1") not in redis.lists


async def test_unknown_run_degrades_safely(redis: FakeRedis) -> None:
    """未初始化的 run 不应抛异常——引擎轮询时遇到脏数据要能继续跑完。"""
    assert await tdc.is_paused(redis, "missing") is False
    assert await tdc.is_cancelled(redis, "missing") is False
    assert await tdc.drain_notes(redis, "missing") == []
