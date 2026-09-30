"""夜间调度触发时间。"""

from datetime import UTC, date, datetime

from app.services.quant_research.scheduler import next_trigger, us_session_date

WEEKDAYS = {0, 1, 2, 3, 4}


def test_next_trigger_same_day_and_next_day():
    after = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)  # 周三
    assert next_trigger(after, 22, 30, WEEKDAYS) == datetime(2026, 9, 30, 22, 30, tzinfo=UTC)
    after = datetime(2026, 9, 30, 23, 0, tzinfo=UTC)
    assert next_trigger(after, 22, 30, WEEKDAYS) == datetime(2026, 10, 1, 22, 30, tzinfo=UTC)


def test_next_trigger_skips_weekend():
    after = datetime(2026, 10, 2, 23, 0, tzinfo=UTC)  # 周五晚
    assert next_trigger(after, 22, 30, WEEKDAYS) == datetime(2026, 10, 5, 22, 30, tzinfo=UTC)


def test_us_session_date():
    assert us_session_date(datetime(2026, 9, 30, 22, 30, tzinfo=UTC)).isoformat() == "2026-09-30"


def test_last_us_session():
    from datetime import datetime

    from app.services.quant_research.scheduler import last_us_session

    # UTC 22:30 前 → 前一个工作日；9-30（周三）06:00 UTC → 9-29（周二）
    assert last_us_session(datetime(2026, 9, 30, 6, 0, tzinfo=UTC)) == date(2026, 9, 29)
    # 收盘缓冲之后 → 当天
    assert last_us_session(datetime(2026, 9, 30, 23, 0, tzinfo=UTC)) == date(2026, 9, 30)
    # 周六凌晨 → 周五；周日凌晨 → 周五
    assert last_us_session(datetime(2026, 10, 3, 6, 0, tzinfo=UTC)) == date(2026, 10, 2)
    assert last_us_session(datetime(2026, 10, 4, 6, 0, tzinfo=UTC)) == date(2026, 10, 2)


def test_lock_ttl_covers_slowest_run():
    """锁 TTL 必须明显大于最慢一轮（首次全量 ~30 分钟），又不能长到重启后长期挡路。"""
    from app.services.quant_research import scheduler

    assert 45 * 60 <= scheduler._LOCK_TTL <= 2 * 3600
    assert scheduler.BOOTSTRAP_RETRY_SECONDS <= scheduler._LOCK_TTL


async def test_align_backfill_drops_radar_snapshots(monkeypatch):
    """对齐改动过行时清掉雷达快照键，让下一轮扫描带着评级重排。"""
    from app.services.quant_research import scheduler

    async def fake_align(market, hour, minute):
        assert (market, hour, minute) == ("us", scheduler.settings.QUANT_BATCH_UTC_HOUR,
                                          scheduler.settings.QUANT_BATCH_UTC_MINUTE)
        return 7

    class FakeRedis:
        def __init__(self):
            self.unlinked: tuple = ()

        def scan_iter(self, match=None, count=None):
            async def gen():
                yield b"signal_radar:ns:us:nasdaq100"
                yield b"signal_radar:wl:us:1:abc"

            return gen()

        async def unlink(self, *keys):
            self.unlinked = keys

    fake = FakeRedis()
    monkeypatch.setattr(scheduler.repo, "align_backfill_timestamps", fake_align)
    monkeypatch.setattr(scheduler, "current_redis", lambda: fake)
    await scheduler._align_backfill()
    assert fake.unlinked == (b"signal_radar:ns:us:nasdaq100", b"signal_radar:wl:us:1:abc")


async def test_align_backfill_no_change_keeps_cache(monkeypatch):
    """没有行需要校正时不碰 Redis。"""
    from app.services.quant_research import scheduler

    async def fake_align(market, hour, minute):
        return 0

    def boom():
        raise AssertionError("不应触碰 Redis")

    monkeypatch.setattr(scheduler.repo, "align_backfill_timestamps", fake_align)
    monkeypatch.setattr(scheduler, "current_redis", boom)
    await scheduler._align_backfill()
