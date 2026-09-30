"""FMP 全局调用预算：分钟额度、批量额度、429 熔断、无 Redis 退化。"""

import pytest

from app.cache import fmp_budget
from app.cache.fmp_budget import BREAKER_KEY, acquire, report_429, reset_local_state


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, int | str] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        self.ttls[key] = ttl

    async def set(self, key, value, ex=None, nx=False):
        self.store[key] = value
        if ex:
            self.ttls[key] = ex
        return True

    async def ttl(self, key):
        return self.ttls.get(key, -2) if key in self.store else -2


class _Clock:
    """可控时钟：sleep 只推进时间，不真睡。"""

    def __init__(self, t=60_000.0):
        self.t = t
        self.slept: list[float] = []

    def now(self):
        return self.t

    async def sleep(self, s):
        self.slept.append(s)
        self.t += s
        # 熔断等待结束后模拟键过期
        return None


@pytest.fixture(autouse=True)
def _reset():
    reset_local_state()
    yield
    reset_local_state()


async def test_batch_blocks_after_limit_until_next_minute():
    r, c = _FakeRedis(), _Clock()
    for _ in range(3):
        await acquire(r, "batch", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=3)
    assert c.slept == []
    await acquire(r, "batch", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=3)
    assert len(c.slept) == 1 and 0 < c.slept[0] <= 60.05
    assert int(c.t // 60) == 60_000 // 60 + 1  # 进入下一分钟


async def test_user_not_limited_by_batch_quota():
    r, c = _FakeRedis(), _Clock()
    for _ in range(3):
        await acquire(r, "batch", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=3)
    for _ in range(5):
        await acquire(r, "user", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=3)
    assert c.slept == []


async def test_total_limit_applies_to_user():
    r, c = _FakeRedis(), _Clock()
    for _ in range(2):
        await acquire(r, "user", now=c.now, sleep=c.sleep, limit_total=2, limit_batch=1)
    await acquire(r, "user", now=c.now, sleep=c.sleep, limit_total=2, limit_batch=1)
    assert len(c.slept) == 1


async def test_429_breaker_pauses_batch_only():
    r, c = _FakeRedis(), _Clock()
    await report_429(r, "batch")
    assert r.store.get(BREAKER_KEY) == "1" and r.ttls[BREAKER_KEY] == fmp_budget.settings.FMP_BATCH_BREAKER_SECONDS

    await acquire(r, "user", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=5)
    assert c.slept == []

    async def sleep_and_expire(s):
        c.slept.append(s)
        c.t += s
        r.store.pop(BREAKER_KEY, None)

    await acquire(r, "batch", now=c.now, sleep=sleep_and_expire, limit_total=10, limit_batch=5)
    assert c.slept == [float(fmp_budget.settings.FMP_BATCH_BREAKER_SECONDS)]


async def test_user_429_does_not_trip_breaker():
    r = _FakeRedis()
    await report_429(r, "user")
    assert BREAKER_KEY not in r.store


async def test_local_fallback_without_redis():
    c = _Clock()
    for _ in range(2):
        await acquire(None, "batch", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=2)
    await acquire(None, "batch", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=2)
    assert len(c.slept) == 1
    await report_429(None, "batch", now=c.now)
    await acquire(None, "batch", now=c.now, sleep=c.sleep, limit_total=10, limit_batch=2)
    assert c.slept[-1] == pytest.approx(fmp_budget.settings.FMP_BATCH_BREAKER_SECONDS)
