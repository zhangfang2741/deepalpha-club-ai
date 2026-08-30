"""交易台运行控制位的 Redis 操作。

key 格式（项目规则：所有 key 必须有 TTL，严禁永不过期）：
  td:ctl:{run_id}    hash   —— paused / cancelled 标志
  td:notes:{run_id}  list   —— 待注入的人工意见队列
  td:seq:{run_id}    string —— 事件单调序号（由 event_bus 使用）
  td:events:{run_id} stream —— 事件流（由 event_bus 使用）

TTL 统一取 settings.TRADING_DESK_EVENT_TTL_SECONDS，与事件流保持一致：
控制位比事件流活得久没有意义，反之则会导致运行中途失去控制。
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings


def control_key(run_id: str) -> str:
    return f"td:ctl:{run_id}"


def notes_key(run_id: str) -> str:
    return f"td:notes:{run_id}"


def _ttl() -> int:
    return settings.TRADING_DESK_EVENT_TTL_SECONDS


async def init_control(redis: Redis, run_id: str) -> None:
    """初始化控制位。运行创建时调用一次。"""
    key = control_key(run_id)
    await redis.hset(key, mapping={"paused": "0", "cancelled": "0"})  # type: ignore[misc]
    await redis.expire(key, _ttl())


async def set_paused(redis: Redis, run_id: str, paused: bool) -> None:
    """置位或清除暂停标志。"""
    key = control_key(run_id)
    await redis.hset(key, mapping={"paused": "1" if paused else "0"})  # type: ignore[misc]
    await redis.expire(key, _ttl())


async def is_paused(redis: Redis, run_id: str) -> bool:
    """当前是否处于暂停态。未初始化的 run 视为未暂停。"""
    return await redis.hget(control_key(run_id), "paused") == b"1"  # type: ignore[misc]


async def set_cancelled(redis: Redis, run_id: str) -> None:
    """请求取消。取消是单向的，一旦置位不可撤回。"""
    key = control_key(run_id)
    await redis.hset(key, mapping={"cancelled": "1"})  # type: ignore[misc]
    await redis.expire(key, _ttl())


async def is_cancelled(redis: Redis, run_id: str) -> bool:
    """当前是否已被请求取消。未初始化的 run 视为未取消。"""
    return await redis.hget(control_key(run_id), "cancelled") == b"1"  # type: ignore[misc]


async def push_note(redis: Redis, run_id: str, text: str) -> None:
    """把一条人工意见排入队列，等引擎在下一个节点边界取走。"""
    key = notes_key(run_id)
    await redis.rpush(key, text)  # type: ignore[misc]
    await redis.expire(key, _ttl())


async def drain_notes(redis: Redis, run_id: str) -> list[str]:
    """取出并清空全部待注入意见。

    读后删而非逐条弹出：引擎在一个节点边界应当一次性看到所有积压意见，
    否则多条意见会被拆散到不同 agent，用户无法预期哪条被谁看到。
    """
    key = notes_key(run_id)
    raw = await redis.lrange(key, 0, -1)  # type: ignore[misc]
    if not raw:
        return []
    await redis.delete(key)
    return [item.decode() if isinstance(item, bytes) else str(item) for item in raw]


async def clear_control(redis: Redis, run_id: str) -> None:
    """运行结束后清理控制位。

    事件流不在此清理——它要保留到 TTL 到期，供断线重连与历史回看。
    """
    await redis.delete(control_key(run_id), notes_key(run_id))
