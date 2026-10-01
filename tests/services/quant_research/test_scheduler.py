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


def test_lock_is_short_and_kept_alive_by_heartbeat():
    """锁靠心跳续期盖住整轮（全量 ~30 分钟），TTL 本身要短：部署重启后旧锁很快过期，冷启动不被长期挡路。"""
    from app.services.quant_research import scheduler

    assert scheduler._LOCK_TTL <= 20 * 60
    assert scheduler._LOCK_RENEW_SECONDS * 2 < scheduler._LOCK_TTL
    assert scheduler.MOAT_LOCK_RENEW_SECONDS * 2 < scheduler.MOAT_LOCK_TTL
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


async def test_bootstrap_rebuilds_when_methodology_version_changed(monkeypatch):
    """方法版本变了 → 部署后立即重跑全量；锁带版本号，不被当天夜间批量锁挡住。"""
    from datetime import date

    from app.services.quant_research import scheduler

    versions = iter(["q4", scheduler.METHODOLOGY_VERSION])
    runs: list[tuple[str, str | None]] = []

    async def fake_latest_date(market):
        return date(2026, 9, 30)

    async def fake_version(market):
        return next(versions)

    async def fake_run_once(kind, day, *, lock_suffix=None):
        runs.append((kind, lock_suffix))

    async def no_align():
        return None

    monkeypatch.setattr(scheduler, "BOOTSTRAP_DELAY_SECONDS", 0)
    monkeypatch.setattr(scheduler, "_align_backfill", no_align)
    monkeypatch.setattr(scheduler.repo, "latest_distribution_date", fake_latest_date)
    monkeypatch.setattr(scheduler.repo, "latest_methodology_version", fake_version)
    monkeypatch.setattr(scheduler, "_run_once", fake_run_once)
    await scheduler._bootstrap_once()
    assert runs == [("us", scheduler.METHODOLOGY_VERSION)]


async def test_bootstrap_skips_when_results_are_current(monkeypatch):
    from datetime import date

    from app.services.quant_research import scheduler

    runs = []

    async def fake_latest_date(market):
        return date(2026, 9, 30)

    async def fake_version(market):
        return scheduler.METHODOLOGY_VERSION

    async def fake_run_once(kind, day, *, lock_suffix=None):
        runs.append(kind)

    async def no_align():
        return None

    monkeypatch.setattr(scheduler, "BOOTSTRAP_DELAY_SECONDS", 0)
    monkeypatch.setattr(scheduler, "_align_backfill", no_align)
    monkeypatch.setattr(scheduler.repo, "latest_distribution_date", fake_latest_date)
    monkeypatch.setattr(scheduler.repo, "latest_methodology_version", fake_version)
    monkeypatch.setattr(scheduler, "_run_once", fake_run_once)
    await scheduler._bootstrap_once()
    assert runs == []


async def test_moat_cold_start_retries_when_locked_and_releases_lock(monkeypatch):
    """部署后冷启动：锁被占（重启前的进程还没过期）就过会儿再试；跑完释放锁。"""
    from app.services.quant_research import scheduler

    class FakeRedis:
        def __init__(self):
            self.keys = {scheduler._moat_lock_key(): "old-process"}
            self.deleted = []

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in self.keys:
                return None
            self.keys[key] = value
            return True

        async def expire(self, key, ttl):
            return True

        async def delete(self, key):
            self.deleted.append(key)
            self.keys.pop(key, None)

    fake = FakeRedis()
    runs = []
    sleeps = []

    async def fake_job(redis):
        runs.append(redis)

    async def fake_sleep(sec):
        sleeps.append(sec)
        if sec == scheduler.MOAT_BOOTSTRAP_RETRY_SECONDS:
            fake.keys.pop(scheduler._moat_lock_key(), None)  # 旧进程的锁过期
        if len(sleeps) > 5:
            raise asyncio.CancelledError

    import asyncio

    monkeypatch.setattr(scheduler, "current_redis", lambda: fake)
    monkeypatch.setattr(scheduler, "run_moat_job", fake_job)
    monkeypatch.setattr(scheduler.asyncio, "sleep", fake_sleep)
    try:
        await scheduler._moat_loop()
    except asyncio.CancelledError:
        pass
    # 先等启动延迟 → 锁被占，等一轮重试 → 跑；之后每天一轮（这里 sleep 立即返回，会空转几轮）
    assert sleeps[:2] == [scheduler.BOOTSTRAP_DELAY_SECONDS, scheduler.MOAT_BOOTSTRAP_RETRY_SECONDS]
    assert runs and fake.deleted and set(fake.deleted) == {scheduler._moat_lock_key()}
