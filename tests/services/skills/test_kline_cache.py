"""K 线缓存 key 测试"""
from app.services.skills.kline import _cache_key


def test_cache_key_includes_user_id():
    assert "u42" in _cache_key(42, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert "public" in _cache_key(None, "NVDA", "2024-01-01", "2025-01-01", "daily")


def test_cache_key_different_for_different_users():
    k1 = _cache_key(1, "NVDA", "2024-01-01", "2025-01-01", "daily")
    k2 = _cache_key(2, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert k1 != k2


def test_cache_key_includes_symbol_and_dates():
    k = _cache_key(42, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert "u42" in k
    assert "NVDA" in k
    assert "2024-01-01" in k
    assert "2025-01-01" in k
    assert "daily" in k