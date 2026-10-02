"""宏观响应缓存 key 带版本：升版本即换新 key，drop_market 的通配与 key 同源。"""
import fnmatch

from app.cache import macro_cache as cache


def test_response_key_carries_version():
    k = cache.response_key("resp", "us", "zh")
    assert k == f"macro:resp:v{cache.RESPONSE_VERSION}:us:zh"


def test_drop_pattern_matches_real_keys():
    assert fnmatch.fnmatch(cache.response_key("sectors", "us", "root", "zh", "2026-10-01"),
                           cache.response_key("sectors", "us", "*"))
    assert not fnmatch.fnmatch(cache.response_key("resp", "cn", "zh"), cache.response_key("resp", "us", "*"))
