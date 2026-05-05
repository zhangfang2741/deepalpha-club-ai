"""ETF 资金流 Redis 缓存操作。

key 格式：
  etf:flows:{symbol}:{period}   — 单只 ETF 历史流量
  etf:list:{period}             — 所有 ETF 汇总列表
TTL：3600 秒（1 小时）
"""

import json
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
        return [FlowDataPoint(**item) for item in json.loads(raw)]
    except Exception as e:
        logger.warning("etf_flows_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_etf_flows_cache(redis: Redis, symbol: str, period: str, flows: List[FlowDataPoint]) -> None:
    """将单只 ETF 资金流数据写入 Redis，TTL = 3600s。"""
    key = f"etf:flows:{symbol}:{period}"
    payload = json.dumps([p.model_dump(mode="json") for p in flows], ensure_ascii=False)
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_flows_cache_set", symbol=symbol, period=period, count=len(flows))


async def get_etf_list_cache(redis: Redis, period: str) -> Optional[List[ETFSummary]]:
    """读取 ETF 汇总列表缓存，未命中返回 None。"""
    key = f"etf:list:{period}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return [ETFSummary(**item) for item in json.loads(raw)]
    except Exception as e:
        logger.warning("etf_list_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_etf_list_cache(redis: Redis, period: str, summaries: List[ETFSummary]) -> None:
    """将 ETF 汇总列表写入 Redis，TTL = 3600s。"""
    key = f"etf:list:{period}"
    payload = json.dumps([s.model_dump(mode="json") for s in summaries], ensure_ascii=False)
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_list_cache_set", period=period, count=len(summaries))


async def get_heatmap_cache(redis: Redis, granularity: str, days: int) -> Optional["HeatmapResponse"]:
    """读取热力图缓存，未命中返回 None。"""
    from app.schemas.etf import HeatmapResponse  # 避免循环导入
    key = f"etf:heatmap:{granularity}:{days}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return HeatmapResponse(**json.loads(raw))
    except Exception as e:
        logger.warning("etf_heatmap_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_heatmap_cache(redis: Redis, granularity: str, days: int, data: "HeatmapResponse") -> None:
    """将热力图数据写入 Redis，TTL = 3600s。"""
    key = f"etf:heatmap:{granularity}:{days}"
    payload = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_heatmap_cache_set", granularity=granularity, days=days)
