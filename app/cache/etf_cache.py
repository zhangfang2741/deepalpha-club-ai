from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from app.schemas.etf import HeatmapResponse

"""ETF 资金流 Redis 缓存操作。

key 格式：
  etf:flows:{symbol}:{period}   — 单只 ETF 历史流量
  etf:list:{period}             — 所有 ETF 汇总列表
TTL：3600 秒（1 小时）

数据使用 zlib 压缩以减少传输量并提高缓存读取速度。
"""

import json
import zlib
from typing import List, Optional

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.etf import ETFSummary, FlowDataPoint

ETF_FLOW_TTL = 3600  # 1 小时


async def get_etf_flows_cache(redis: Redis, symbol: str, period: str) -> Optional[List[FlowDataPoint]]:
    """读取单只 ETF 资金流缓存，未命中返回 None。"""
    key = f"etf:flows:{symbol}:{period}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        # 确保 raw 是 bytes 类型
        if isinstance(raw, str):
            raw = raw.encode("latin-1")
        elif not isinstance(raw, bytes):
            raw = bytes(raw)
        # 尝试解压（兼容新旧格式）
        try:
            decompressed = zlib.decompress(raw)
            data = json.loads(decompressed)
        except Exception:
            data = json.loads(raw)
        return [FlowDataPoint(**item) for item in data]
    except Exception as e:
        logger.warning("etf_flows_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_etf_flows_cache(redis: Redis, symbol: str, period: str, flows: List[FlowDataPoint]) -> None:
    """将单只 ETF 资金流数据写入 Redis（使用 zlib 压缩），TTL = 3600s。"""
    key = f"etf:flows:{symbol}:{period}"
    json_str = json.dumps([p.model_dump(mode="json") for p in flows], ensure_ascii=False)
    payload = zlib.compress(json_str.encode("utf-8"))
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_flows_cache_set", symbol=symbol, period=period, count=len(flows), size_bytes=len(payload))


async def get_etf_list_cache(redis: Redis, period: str) -> Optional[List[ETFSummary]]:
    """读取 ETF 汇总列表缓存，未命中返回 None。"""
    key = f"etf:list:{period}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        # 确保 raw 是 bytes 类型
        if isinstance(raw, str):
            raw = raw.encode("latin-1")
        elif not isinstance(raw, bytes):
            raw = bytes(raw)
        try:
            decompressed = zlib.decompress(raw)
            data = json.loads(decompressed)
        except Exception:
            data = json.loads(raw)
        return [ETFSummary(**item) for item in data]
    except Exception as e:
        logger.warning("etf_list_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_etf_list_cache(redis: Redis, period: str, summaries: List[ETFSummary]) -> None:
    """将 ETF 汇总列表写入 Redis（使用 zlib 压缩），TTL = 3600s。"""
    key = f"etf:list:{period}"
    json_str = json.dumps([s.model_dump(mode="json") for s in summaries], ensure_ascii=False)
    payload = zlib.compress(json_str.encode("utf-8"))
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_list_cache_set", period=period, count=len(summaries), size_bytes=len(payload))


async def get_heatmap_cache(redis: Redis, granularity: str, days: int) -> Optional["HeatmapResponse"]:
    """读取热力图缓存，未命中返回 None。"""
    from app.schemas.etf import HeatmapResponse  # 避免循环导入
    key = f"etf:heatmap:{granularity}:{days}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        # 确保 raw 是 bytes 类型
        if isinstance(raw, str):
            raw = raw.encode("latin-1")
        elif not isinstance(raw, bytes):
            raw = bytes(raw)
        try:
            decompressed = zlib.decompress(raw)
            data = json.loads(decompressed)
        except Exception:
            data = json.loads(raw)
        return HeatmapResponse(**data)
    except Exception as e:
        logger.warning("etf_heatmap_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_heatmap_cache(redis: Redis, granularity: str, days: int, data: "HeatmapResponse") -> None:
    """将热力图数据写入 Redis（使用 zlib 压缩），TTL = 3600s。"""
    key = f"etf:heatmap:{granularity}:{days}"
    json_str = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
    payload = zlib.compress(json_str.encode("utf-8"))
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_heatmap_cache_set", granularity=granularity, days=days, size_bytes=len(payload))


async def get_deviation_cache(redis: Redis, days: int) -> Optional["DeviationScoreResponse"]:
    """读取偏离分缓存，未命中返回 None。key: etf:deviation:{days}"""
    from app.schemas.etf import DeviationScoreResponse  # 避免循环导入
    key = f"etf:deviation:{days}"
    raw = await redis.get(key)
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
        return DeviationScoreResponse(**data)
    except Exception as e:
        logger.warning("etf_deviation_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_deviation_cache(redis: Redis, days: int, data: "DeviationScoreResponse") -> None:
    """将偏离分数据写入 Redis（使用 zlib 压缩），TTL = 3600s。key: etf:deviation:{days}"""
    key = f"etf:deviation:{days}"
    json_str = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
    payload = zlib.compress(json_str.encode("utf-8"))
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_deviation_cache_set", days=days, size_bytes=len(payload))
