"""API 测试的公共夹具。

关掉限流是必须的，不是图省事：limiter 在 VALKEY_HOST 有配置时会用真实的
Upstash Redis 做存储（见 app/core/limiter.py），计数器跨进程持久化。不关的话
有两个后果——测试会往共享的线上 Redis 里写计数，以及同一个测试文件跑第二遍
时因为额度耗尽而返回 429，断言全变成随机结果。

限流本身的行为不在这层测：它是 slowapi 提供的，我们只配置额度。
"""

import pytest

from app.core.limiter import limiter


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """整个 tests/api 目录下的测试都不走限流。"""
    original = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = original
