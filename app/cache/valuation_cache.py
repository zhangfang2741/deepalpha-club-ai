"""行业估值 Redis 缓存操作。

key: valuation:sectors
TTL: 14400 秒（4 小时）—— 行业 PE 变动慢，可缓存较长时间。
"""

from __future__ import annotations

import json
import zlib
from typing import TYPE_CHECKING, Optional

from redis.asyncio import Redis

from app.core.logging import logger

if TYPE_CHECKING:
    from app.schemas.valuation import SectorValuationResponse

_KEY = "valuation:sectors"
_TTL = 14400  # 4 小时


async def get_valuation_cache(redis: Redis) -> Optional["SectorValuationResponse"]:
    """读取行业估值缓存，未命中或解析失败返回 None。"""
    from app.schemas.valuation import SectorValuationResponse

    raw = await redis.get(_KEY)
    if raw is None:
        return None
    try:
        if isinstance(raw, str):
            raw = raw.encode("latin-1")
        elif not isinstance(raw, bytes):
            raw = bytes(raw)
        try:
            decompressed = zlib.decompress(raw)
            data = json.loads(decompressed)
        except Exception:
            data = json.loads(raw)
        return SectorValuationResponse(**data)
    except Exception as e:
        logger.warning("valuation_cache_deserialize_error", key=_KEY, error=str(e))
        return None


async def set_valuation_cache(redis: Redis, data: "SectorValuationResponse") -> None:
    """将行业估值数据写入 Redis（zlib 压缩），TTL = 4 小时。"""
    json_str = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
    payload = zlib.compress(json_str.encode("utf-8"))
    await redis.set(_KEY, payload, ex=_TTL)
    logger.info("valuation_cache_set", sectors=len(data.sectors), size_bytes=len(payload))
