"""K 线缓存 key 与 TTL 测试."""
from app.services.skills.kline import _cache_key


def test_cache_key_includes_user_id():
    """缓存键区分登录用户与匿名."""
    assert "u42" in _cache_key(42, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert "public" in _cache_key(None, "NVDA", "2024-01-01", "2025-01-01", "daily")


def test_cache_key_different_for_different_users():
    """不同用户的缓存键不同."""
    k1 = _cache_key(1, "NVDA", "2024-01-01", "2025-01-01", "daily")
    k2 = _cache_key(2, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert k1 != k2


def test_cache_key_includes_symbol_and_dates():
    """缓存键包含代码与起止日期."""
    k = _cache_key(42, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert "u42" in k
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
    assert _cache_ttl_for("30min", "2026-09-01", today=today) == 60 * 15
