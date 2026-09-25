"""K 线缓存 key 与 TTL 测试."""
from app.services.skills.kline import _cache_key


def test_cache_key_shared_across_users():
    """K 线与用户无关，所有用户（含雷达扫描的匿名调用）共用同一份缓存.

    回归：按用户分缓存时，雷达（public）与用户点进详情（u42）各自在不同时刻取数，
    盘中未收盘K线不同 → 同一只股票两边笔与买卖点不一致（雷达有 9.22 买点、详情没有）。
    """
    keys = {_cache_key(uid, "NVDA", "2024-01-01", "2025-01-01", "daily") for uid in (None, 1, 42)}
    assert len(keys) == 1


def test_cache_key_includes_symbol_and_dates():
    """缓存键包含代码与起止日期."""
    k = _cache_key(42, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert "NVDA" in k
    assert "2024-01-01" in k
    assert "2025-01-01" in k
    assert "daily" in k

def test_daily_ttl_short_when_range_reaches_latest_session():
    """截止日覆盖最近交易日（UTC 昨天及以后）的日线只缓存 30 分钟.

    回归：A 股 15:00 收盘 = UTC 07:00。北京时间白天扫描拿到的「截止今天」数据还没有
    当日K线，却按 24h 缓存，收盘后整天都读到旧数据——雷达时间轴缺最近交易日。
    """
    from datetime import date

    from app.services.skills.kline import _cache_ttl_for

    today = date(2026, 9, 24)
    assert _cache_ttl_for("daily", "2026-09-24", today=today) == 1800
    assert _cache_ttl_for("daily", "2026-09-23", today=today) == 1800  # 美股晚间用户本地日期落后一天
    assert _cache_ttl_for("daily", "2026-09-25", today=today) == 1800  # 东八区用户本地日期领先一天
    assert _cache_ttl_for("daily", "2026-09-01", today=today) == 3600 * 24  # 纯历史区间
    assert _cache_ttl_for("weekly", "2026-09-24", today=today) == 1800
    assert _cache_ttl_for("30min", "2026-09-01", today=today) == 60 * 3
