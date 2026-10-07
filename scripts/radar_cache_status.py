"""检查信号雷达缓存是否就绪（冷启动 / 部署后用）。

用法（在能连到线上 Redis 的环境里，读取与后端相同的 VALKEY_* 环境变量）：
    uv run python scripts/radar_cache_status.py

逐个 (市场, 指数, 口径) 列出：主快照是否存在、剩余 TTL、是否陈旧、天数 / 补算中只数，以及免费示例日快照是否存在 / 陈旧。
「缺」= 用户第一次打开会看到「正在扫描」；全部「有」说明冷启动预热已完成。
"""
import asyncio

from app.cache.client import close_redis, current_redis, init_redis
from app.services.signal_radar import scheduler
from app.services.signal_radar.service import (
    _cache_key,
    _cache_ttl,
    demo_cache_is_stale,
    peek_cache_entry,
    read_demo_cache,
)


async def main() -> None:
    """列出全部 (市场, 指数, 口径) 的缓存状态。"""
    await init_redis()
    redis = current_redis()
    if redis is None:
        raise SystemExit("连不上 Redis：检查 VALKEY_HOST / VALKEY_PASSWORD / VALKEY_SSL")
    rows = []
    for u in scheduler._target_universes():
        for mode in scheduler._modes():
            cached, stale = await peek_cache_entry(redis, u.market, u.key, mode)
            ttl = await redis.ttl(_cache_key(u.market, u.key, mode))
            demo = await read_demo_cache(redis, u.market, u.key, mode)
            demo_stale = bool(demo) and await demo_cache_is_stale(redis, u.market, u.key, demo, mode)
            rows.append((u.market, u.key, mode, cached, stale, ttl, demo, demo_stale))
    print(f"{'市场':<4}{'指数':<14}{'口径':<8}{'主快照':<8}{'陈旧':<6}{'剩余':<9}{'天数':<5}{'补算':<5}示例日")
    missing = 0
    for market, key, mode, cached, stale, ttl, demo, demo_stale in rows:
        main = "有" if cached else "缺"
        demo_s = "缺" if demo is None else ("陈旧" if demo_stale else "有")
        missing += (cached is None) + (demo is None)
        days = len(cached.days) if cached else "-"
        pend = (cached.pending_symbols or 0) if cached else "-"
        remain = f"{ttl // 3600}h" if ttl and ttl > 0 else "-"
        print(f"{market:<4}{key:<14}{mode:<8}{main:<8}{'是' if stale else '否':<6}{remain:<9}{days!s:<5}{pend!s:<5}{demo_s}")
    print(f"\n缺失 {missing} 项；主快照总 TTL {_cache_ttl() // 3600}h")
    await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
