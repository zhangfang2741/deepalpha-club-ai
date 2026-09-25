"""信号雷达纯聚合逻辑单测（无 IO）。"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.signals import Signal
from app.services.signal_radar import service as svc
from app.services.signal_radar.service import (
    RawSignal,
    build_days,
    build_signal_history,
    display_rank,
    signal_strength,
)


def _sig(sig_type: str, time: str, price: float, strength: str = "medium") -> Signal:
    return Signal(
        type=sig_type, time=time, price=price, strength=strength,
        divergence=None, description="", confirmed=True, lang="zh",
    )


def _raw(symbol: str, day: str, side: str, strength: float, level: int = 1) -> RawSignal:
    return RawSignal(
        symbol=symbol, name=symbol, side=side, label="一买" if side == "buy" else "一卖",
        signal_type=f"{side}{level}", date=day, price=10.0,
        strength=strength, bias="bullish" if side == "buy" else "bearish",
        signal_strength="medium", confirmed=True,
        pivot_stage_depth=0.55,  # 这批测试只关心 display_rank/build_days 的排序与淘汰逻辑，
        # 都不读这个字段，给个中性占位值即可
    )


class TestSignalStrength:
    def test_known_labels(self):
        assert signal_strength("strong") == 0.8
        assert signal_strength("medium") == 0.55
        assert signal_strength("weak") == 0.35

    def test_unknown_label_defaults_to_mid(self):
        assert signal_strength("???") == 0.5


class TestBuildSignalHistory:
    def test_empty_when_no_signals(self):
        r = ChanAnalysisResult(symbol="X", bars_count=100)
        assert build_signal_history("X", "测试", r) == []

    def test_returns_all_signals_sorted_by_date(self):
        s1 = _sig("buy1", "2026-09-01", 10.0)
        s2 = _sig("sell1", "2026-09-10", 12.0)
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[s2, s1])
        history = build_signal_history("NVDA", "英伟达", r)
        assert [h.date for h in history] == ["2026-09-01", "2026-09-10"]
        assert history[0].side == "buy"
        assert history[1].side == "sell"
        assert all(h.name == "英伟达" for h in history)

    def test_date_is_truncated_to_day(self):
        sig = _sig("buy1", "2026-09-19T00:00:00", 12.0)
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig])
        history = build_signal_history("X", "x", r)
        assert history[0].date == "2026-09-19"

    def test_strength_from_signal_label_not_score(self):
        sig = _sig("sell1", "2026-09-18", 50.0, strength="strong")
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig])
        history = build_signal_history("AAPL", "苹果", r)
        assert history[0].strength == signal_strength("strong")
        assert history[0].bias == "bearish"

    def test_pivot_stage_depth_defaults_when_no_pivot(self):
        """结构没有笔/中枢时取不到阶段，深浅退回中性默认值，不假装知道阶段。"""
        sig = _sig("buy1", "2026-09-18", 10.0)
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig])
        history = build_signal_history("X", "x", r)
        assert history[0].pivot_stage_depth == svc._DEFAULT_STAGE_DEPTH

    def test_pivot_stage_depth_reflects_phase_on_signals_own_date(self):
        """深浅按信号自己发生那天回溯的中枢阶段算，不是"今天"的阶段快照。"""
        from app.services.chan.fractal import Fractal, MergedCandle
        from app.services.chan.pivot import Pivot
        from app.services.chan.stroke import Stroke

        def mc(idx: int, price: float) -> MergedCandle:
            return MergedCandle(idx=idx, time=f"D{idx:03d}", open=price, high=price + 1,
                                 low=price - 1, close=price, raw_start=idx, raw_end=idx)

        def fx(kind: str, idx: int, price: float) -> Fractal:
            mid = mc(idx, price)
            return Fractal(type=kind, candle=mid, left=mc(idx - 1, price), right=mc(idx + 1, price))

        def st(direction: str, idx: int, p0: float, p1: float) -> Stroke:
            sk = "bottom" if direction == "up" else "top"
            ek = "top" if direction == "up" else "bottom"
            return Stroke(direction=direction, start=fx(sk, idx * 10, p0), end=fx(ek, idx * 10 + 5, p1))

        # 形成中枢(zg=98,zd=90) -> 震荡延伸 -> 真正突破 -> 回踩确认三买
        strokes = [
            st("down", 0, 100, 90), st("up", 1, 90, 98), st("down", 2, 98, 92),
            st("up", 3, 92, 96), st("down", 4, 96, 91),
            st("up", 5, 91, 110), st("down", 6, 110, 101),
        ]
        pivot = Pivot(zg=98, zd=90, gg=100, dd=89, start_time=strokes[0].start_time,
                      end_time=strokes[6].end_time, level="stroke", elements=strokes[:7])
        r = ChanAnalysisResult(symbol="X", bars_count=100)
        r.strokes = strokes
        r.stroke_pivots = [pivot]
        r.divergences = []
        r.signals = [
            _sig("buy2", strokes[2].end_time, 92.0),   # 中枢刚形成那天
            _sig("buy3", strokes[6].end_time, 101.0),  # 确认三买那天（已离开中枢）
        ]
        history = build_signal_history("X", "x", r)
        forming_signal = next(h for h in history if h.date == strokes[2].end_time[:10])
        confirmed_signal = next(h for h in history if h.date == strokes[6].end_time[:10])
        assert forming_signal.pivot_stage_depth == svc._PIVOT_STAGE_DEPTH["pivot_forming"]
        assert confirmed_signal.pivot_stage_depth == svc._PIVOT_STAGE_DEPTH["retrace_confirmed"]
        assert forming_signal.pivot_stage_depth != confirmed_signal.pivot_stage_depth


class TestBuildDays:
    def test_signal_stays_active_until_superseded(self):
        """一只股票 09-01 出现买点、09-10 前无新信号——09-01~09-09 每天都在场，09-10 起换新信号。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5), _raw("A", "2026-09-10", "sell", 0.9)]
        days = build_days([history], ["2026-09-05", "2026-09-01"], top_n=10)
        assert [s.date for s in days[0].signals] == ["2026-09-01"]
        assert days[0].signals[0].side == "buy"
        assert [s.date for s in days[1].signals] == ["2026-09-01"]

    def test_symbol_absent_before_its_first_signal(self):
        history = [_raw("A", "2026-09-10", "buy", 0.5)]
        days = build_days([history], ["2026-09-05"], top_n=10)
        assert days[0].signals == []
        assert days[0].buy_count == 0

    def test_top_n_limits_and_sorts_by_strength_when_same_level(self):
        """同为一类时，重要度随强弱单调——前 top_n 仍按 strength 从高到低。"""
        histories = [[_raw(f"S{i}", "2026-09-19", "buy", i / 20)] for i in range(15)]
        days = build_days(histories, ["2026-09-19"], top_n=10)
        assert len(days) == 1
        signals = days[0].signals
        assert len(signals) == 10
        strengths = [s.strength for s in signals]
        assert strengths == sorted(strengths, reverse=True)
        assert min(strengths) >= 5 / 20

    def test_one_level_cannot_monopolize_the_board(self):
        """哪怕某个级别信号又多又强，也不能把其它级别全部挤出榜单。

        回归：display_rank 单纯按分数排序时，无论把"确定性"权重给哪个级别
        最高，那个级别都会把榜单挤满（实测把权重给三类后，看板几乎清一色
        三买三卖）。换成分桶轮流选取后，即便三类信号数量和强弱都占绝对
        优势，一类信号只要存在就该有名额。
        """
        histories = (
            [[_raw(f"L3-{i}", "2026-09-19", "buy", 0.9, level=3)] for i in range(10)]
            + [[_raw("L1-ONLY", "2026-09-19", "buy", 0.9, level=1)]]
        )
        days = build_days(histories, ["2026-09-19"], top_n=3)
        assert "L1-ONLY" in {s.symbol for s in days[0].signals}

    def test_round_robin_fills_from_each_level_when_available(self):
        """三个级别都有余量时，按级别轮流各取一个，画面同时看得到一二三类。"""
        histories = [
            [_raw("A1", "2026-09-19", "buy", 0.9, level=1)],
            [_raw("A2", "2026-09-19", "buy", 0.5, level=1)],
            [_raw("B1", "2026-09-19", "buy", 0.9, level=2)],
            [_raw("B2", "2026-09-19", "buy", 0.5, level=2)],
            [_raw("C1", "2026-09-19", "buy", 0.9, level=3)],
            [_raw("C2", "2026-09-19", "buy", 0.5, level=3)],
        ]
        days = build_days(histories, ["2026-09-19"], top_n=3)
        levels = sorted(s.signal_type[-1] for s in days[0].signals)
        assert levels == ["1", "2", "3"]

    def test_exhausted_bucket_does_not_waste_a_slot(self):
        """某个级别的信号提前取完，剩下名额继续从其它级别补齐，不会空着。"""
        histories = (
            [[_raw("ONLY_L1", "2026-09-19", "buy", 0.9, level=1)]]
            + [[_raw(f"L3-{i}", "2026-09-19", "buy", 0.9, level=3)] for i in range(5)]
        )
        days = build_days(histories, ["2026-09-19"], top_n=3)
        assert len(days[0].signals) == 3


class TestDisplayRank:
    def test_level_read_from_signal_type_suffix(self):
        assert display_rank(_raw("X", "2026-09-19", "buy", 0.5, level=3)) > display_rank(
            _raw("X", "2026-09-19", "buy", 0.5, level=2)
        )
        assert display_rank(_raw("X", "2026-09-19", "buy", 0.5, level=2)) > display_rank(
            _raw("X", "2026-09-19", "buy", 0.5, level=1)
        )

    def test_potential_space_can_outweigh_strength(self):
        """0.6/0.4 权重下，三类弱(大而淡)重要度高于一类强(小而深)。"""
        big_pale = _raw("BIG", "2026-09-19", "buy", 0.35, level=3)
        small_dark = _raw("SMALL", "2026-09-19", "buy", 0.8, level=1)
        assert display_rank(big_pale) > display_rank(small_dark)

    def test_counts_buy_and_sell(self):
        histories = [
            [_raw("A", "2026-09-19", "buy", 0.9)],
            [_raw("B", "2026-09-19", "buy", 0.8)],
            [_raw("C", "2026-09-19", "sell", 0.7)],
        ]
        days = build_days(histories, ["2026-09-19"], top_n=10)
        assert days[0].buy_count == 2
        assert days[0].sell_count == 1

    def test_returns_one_entry_per_requested_day_in_order(self):
        histories = [[_raw("A", "2026-09-10", "buy", 0.5)]]
        requested = ["2026-09-17", "2026-09-16", "2026-09-15"]
        days = build_days(histories, requested, top_n=10)
        assert [d.date for d in days] == requested

    def test_no_histories_still_returns_a_day_with_zero_counts(self):
        """trading_days 独立传入（来自 ETF 日历）：无任何股票有信号时，那天仍要出现（空桶），不能连日期都消失。"""
        days = build_days([], ["2026-09-19"], top_n=10)
        assert len(days) == 1
        assert days[0].date == "2026-09-19"
        assert days[0].signals == []

    def test_no_requested_days_returns_empty(self):
        history = [_raw("A", "2026-09-19", "buy", 0.5)]
        assert build_days([history], [], top_n=10) == []

    def test_signal_expires_after_max_age(self):
        """在场信号诞生超过 max_age_days 天后不再展示（09-01 买点在 34 天后的 10-05 已过期）。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5)]
        days = build_days([history], ["2026-10-05"], top_n=10, max_age_days=30)
        assert days[0].signals == []
        assert days[0].buy_count == 0

    def test_signal_visible_at_exactly_max_age(self):
        """恰好等于 max_age_days 天仍在场（09-01 买点在 30 天后的 10-01 边界含、应显示）。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5)]
        days = build_days([history], ["2026-10-01"], top_n=10, max_age_days=30)
        assert [s.date for s in days[0].signals] == ["2026-09-01"]

    def test_expiry_is_relative_to_each_viewed_day(self):
        """过期相对每个展示日各自判断：同条 09-01 信号翻看 09-15 在场、10-05 已过期。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5)]
        days = build_days([history], ["2026-10-05", "2026-09-15"], top_n=10, max_age_days=30)
        assert days[0].signals == []  # 10-05：过期
        assert [s.date for s in days[1].signals] == ["2026-09-01"]  # 09-15：在场


class TestCacheTiming:
    """缓存 TTL 与陈旧判定（方案1 消除过期空窗 + 方案2 stale-while-revalidate）。"""

    def test_ttl_comfortably_exceeds_prewarm_interval(self, monkeypatch):
        """TTL 必须明显长于预热间隔，否则会出现'过期了但下一轮预热还没跑'的空窗。"""
        monkeypatch.setattr(settings, "SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS", 21600)
        assert svc._cache_ttl() > settings.SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS
        assert svc._cache_ttl() == 21600 * 2

    def test_ttl_never_below_floor(self, monkeypatch):
        """预热间隔调得很短时，TTL 仍有 6h 下限兜底。"""
        monkeypatch.setattr(settings, "SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS", 60)
        assert svc._cache_ttl() == svc._CACHE_TTL_FLOOR

    def test_stale_threshold_between_interval_and_ttl(self, monkeypatch):
        """陈旧阈值落在 (interval, ttl) 之间：正常预热够不着，预热停摆才触发自愈刷新。"""
        monkeypatch.setattr(settings, "SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS", 21600)
        assert settings.SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS < svc._cache_stale_after()
        assert svc._cache_stale_after() < svc._cache_ttl()


class _FakeRedis:
    """只实现所需命令的内存替身：set(ex=) / get / ttl。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None, keepttl: bool = False) -> None:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        elif not keepttl:
            self.ttls.pop(key, None)  # 与 Redis 一致：不带 EX/KEEPTTL 的 SET 会清掉过期时间

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def ttl(self, key: str) -> int:
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)


def _write(redis: _FakeRedis, key: str, remaining_ttl: int) -> None:
    """直接往替身里塞一条缓存并指定剩余 TTL，模拟不同新鲜度。"""
    redis.store[key] = "{}"
    redis.ttls[key] = remaining_ttl


class TestCacheStaleness:
    """_cache_is_stale：按剩余 TTL 反推年龄判断陈旧。"""

    @pytest.fixture(autouse=True)
    def _fixed_interval(self, monkeypatch):
        monkeypatch.setattr(settings, "SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS", 21600)

    async def test_fresh_cache_not_stale(self):
        """刚写入（剩余 TTL 接近满）→ 不陈旧，不触发刷新。"""
        redis = _FakeRedis()
        key = svc._cache_key("us", "nasdaq100")
        _write(redis, key, remaining_ttl=svc._cache_ttl())
        assert await svc._cache_is_stale(redis, "us", "nasdaq100") is False

    async def test_old_cache_is_stale(self):
        """剩余 TTL 很小（年龄已超阈值）→ 陈旧，触发后台刷新。"""
        redis = _FakeRedis()
        key = svc._cache_key("us", "nasdaq100")
        _write(redis, key, remaining_ttl=svc._cache_ttl() - svc._cache_stale_after() - 1)
        assert await svc._cache_is_stale(redis, "us", "nasdaq100") is True

    async def test_missing_ttl_treated_as_stale(self):
        """无过期时间（-1）→ 当作陈旧，好让刷新把带正常 TTL 的缓存重建起来。"""
        redis = _FakeRedis()
        redis.store[svc._cache_key("us", "nasdaq100")] = "{}"  # 未设 ttl
        assert await svc._cache_is_stale(redis, "us", "nasdaq100") is True

    async def test_ttl_read_error_not_stale(self):
        """读 TTL 抛错 → 保守当作不陈旧，避免无谓地反复触发刷新。"""

        class _BoomRedis(_FakeRedis):
            async def ttl(self, key: str) -> int:
                raise RuntimeError("boom")

        assert await svc._cache_is_stale(_BoomRedis(), "us", "nasdaq100") is False


class TestAttachSubLevels:
    """只给最新一天入榜气泡补算次级别结论；缺日线结果或补算失败时留空、不影响榜单。"""

    def _day(self):
        from app.schemas.signal_radar import RadarDayOut, RadarSignalOut

        def sig(sym):
            return RadarSignalOut(symbol=sym, name=sym, side="buy", label="一买", signal_type="buy1",
                                  date="2026-09-24", price=1.0, strength=0.5, bias="bullish",
                                  signal_strength="medium", confirmed=True, pivot_stage_depth=0.5)
        return RadarDayOut(date="2026-09-24", buy_count=3, sell_count=0,
                           signals=[sig("AAPL"), sig("NVDA"), sig("MSFT")])

    async def test_fills_verdict_via_shared_entry(self, monkeypatch):
        """走与详情页相同的 current_sub_level（refresh=True、中英各一份）；补算失败留空。"""
        from app.schemas.chan import SubLevelResponse
        from app.services.signal_radar import service

        calls = []

        async def fake_current(symbol, parent_freq="daily", **kwargs):
            calls.append((symbol, parent_freq, kwargs.get("lang"), kwargs.get("refresh")))
            if symbol == "NVDA":
                raise RuntimeError("boom")
            return SubLevelResponse(symbol=symbol, daily_bias="bullish", daily_bias_label="偏强", sub_freq="30min",
                                    verdict="resonance_buy", verdict_label="共振买点", detail="")

        monkeypatch.setattr(service, "current_sub_level", fake_current)
        day = self._day()
        await service.attach_sub_levels(day, end_date="2026-09-24", user_id=None, redis=None)

        by_sym = {s.symbol: s for s in day.signals}
        assert by_sym["AAPL"].sub_level_verdict == "resonance_buy"
        assert by_sym["AAPL"].sub_level_label == "共振买点"
        assert by_sym["NVDA"].sub_level_verdict is None   # 补算失败留空
        assert ("AAPL", "daily", "zh", True) in calls and ("AAPL", "daily", "en", True) in calls


class TestSubLevelRefresh:
    """共振标记独立刷新：盘中每 30 分钟只重算最新一天入榜气泡的次级别，写回快照保留原 TTL。"""

    def _snapshot(self, day: str = "2026-09-24"):
        from app.schemas.signal_radar import RadarDayOut, RadarSignalOut, SignalRadarResponse

        def sig(sym):
            return RadarSignalOut(symbol=sym, name=sym, side="sell", label="二卖", signal_type="sell2",
                                  date=day, price=1.0, strength=0.5, bias="bearish",
                                  signal_strength="medium", confirmed=True, pivot_stage_depth=0.5)
        return SignalRadarResponse(market="us", universe="nasdaq100", etf_name="QQQ", universe_size=2,
                                   as_of=day, top_n=12, days=[RadarDayOut(date=day, buy_count=0, sell_count=2,
                                                                          signals=[sig("AAPL"), sig("NVDA")])])

    def _patch(self, monkeypatch, on_sub=None):
        from app.schemas.chan import SubLevelResponse

        async def fake_current(symbol, parent_freq="daily", **kwargs):
            if on_sub:
                await on_sub()
            return SubLevelResponse(symbol=symbol, daily_bias="bearish", daily_bias_label="偏弱", sub_freq="30min",
                                    verdict="resonance_sell", verdict_label="共振卖点", detail="")

        monkeypatch.setattr(svc, "current_sub_level", fake_current)

    async def test_refresh_updates_verdicts_and_keeps_ttl(self, monkeypatch):
        from datetime import UTC, datetime

        from app.schemas.signal_radar import SignalRadarResponse

        redis = _FakeRedis()
        key = svc._cache_key("us", "nasdaq100")
        redis.store[key] = self._snapshot().model_dump_json()
        redis.ttls[key] = 1000
        self._patch(monkeypatch)

        now = datetime(2026, 9, 24, 15, 0, tzinfo=UTC)
        assert await svc.refresh_sub_levels("us", "nasdaq100", redis=redis, now=now) is True

        data = SignalRadarResponse.model_validate_json(redis.store[key])
        assert {s.sub_level_verdict for s in data.days[0].signals} == {"resonance_sell"}
        assert data.sub_level_as_of == "2026-09-24T15:00:00+00:00"
        assert redis.ttls[key] == 1000  # 保留原 TTL，不打乱「陈旧」判断与全量预热节奏

    async def test_refresh_skips_when_snapshot_replaced_meanwhile(self, monkeypatch):
        """补算期间全量预热写入了新一天的快照：不能用旧气泡覆盖它。"""
        from datetime import UTC, datetime

        from app.schemas.signal_radar import SignalRadarResponse

        redis = _FakeRedis()
        key = svc._cache_key("us", "nasdaq100")
        redis.store[key] = self._snapshot("2026-09-24").model_dump_json()
        newer = self._snapshot("2026-09-25").model_dump_json()

        async def replace():
            redis.store[key] = newer

        self._patch(monkeypatch, on_sub=replace)
        now = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)
        assert await svc.refresh_sub_levels("us", "nasdaq100", redis=redis, now=now) is False
        assert SignalRadarResponse.model_validate_json(redis.store[key]).days[0].date == "2026-09-25"

    async def test_refresh_without_cache_is_noop(self):
        assert await svc.refresh_sub_levels("us", "nasdaq100", redis=_FakeRedis()) is False


def test_market_session_windows():
    """开盘时段（含收盘后半小时，拿到收盘那根 30 分钟K线）才刷新；周末不刷。"""
    from datetime import UTC, datetime

    def at(h, m=0, day=24):  # 2026-09-24 周四；26 周六
        return datetime(2026, 9, day, h, m, tzinfo=UTC)

    assert svc.market_session_active("cn", at(3)) is True       # 北京 11:00
    assert svc.market_session_active("cn", at(7, 20)) is True    # 收盘后 20 分钟
    assert svc.market_session_active("cn", at(12)) is False
    assert svc.market_session_active("hk", at(8, 20)) is True    # 港股 16:00 收盘后
    assert svc.market_session_active("us", at(15)) is True       # 美东 11:00
    assert svc.market_session_active("us", at(2)) is False
    assert svc.market_session_active("us", at(15, day=26)) is False  # 周六


async def test_refresh_loop_only_touches_open_markets(monkeypatch):
    """调度一轮：只刷新此刻开盘的市场。"""
    from datetime import UTC, datetime

    from app.services.signal_radar import scheduler

    called = []

    async def fake_refresh(market, key, **kwargs):
        called.append(market)
        return True

    class _FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 24, 3, 0, tzinfo=UTC)  # 北京 11:00：A/港股开盘、美股休市

    monkeypatch.setattr(scheduler, "refresh_sub_levels", fake_refresh)
    monkeypatch.setattr(scheduler, "current_redis", lambda: object())
    monkeypatch.setattr(scheduler, "datetime", _FixedDT)
    await scheduler._refresh_sub_levels_once()
    assert called and set(called) <= {"cn", "hk"}


def test_trading_days_from_constituents_not_limited_by_lagging_etf():
    """交易日按成分股日线确定：参考 ETF 数据慢一天（科创50 588000 只到 9.23）不能让时间轴缺 9.24。"""
    per_symbol = [["2026-09-22", "2026-09-23", "2026-09-24"]] * 8 + [["2026-09-22", "2026-09-23"]] * 2
    etf = ["2026-09-22", "2026-09-23"]
    days = svc.trading_days_from_constituents(per_symbol, etf_dates=etf, cutoff="2026-09-01",
                                              end_date="2026-09-25", limit=30)
    assert days[0] == "2026-09-24"
    assert days == ["2026-09-24", "2026-09-23", "2026-09-22"]


def test_trading_days_ignore_dates_only_few_symbols_have():
    """个别标的的异常日期（停牌复牌错位、数据源串日）不算交易日：需 >=30% 成分股都有。"""
    per_symbol = [["2026-09-23", "2026-09-24"]] * 9 + [["2026-09-23", "2026-09-24", "2026-09-25"]]
    days = svc.trading_days_from_constituents(per_symbol, etf_dates=[], cutoff="2026-09-01",
                                              end_date="2026-09-25", limit=30)
    assert days == ["2026-09-24", "2026-09-23"]


def test_prewarm_scans_stalest_universe_first(monkeypatch):
    """频繁重启时先扫缓存最旧的 universe，A 股/港股不会一直排在美股后面轮不到。"""
    import asyncio

    from app.services.signal_radar import scheduler

    order = []
    ttl = {"us:nasdaq100": 40000, "cn:star50": 100, "hk:hstech": 5000}

    class _R:
        async def ttl(self, key):
            for k, v in ttl.items():
                if key.endswith(k):
                    return v
            return -2

    async def fake_compute(market, *, redis, user_id, universe_key):
        order.append(f"{market}:{universe_key}")

        class _Resp:
            days = []
        return _Resp()

    monkeypatch.setattr(scheduler, "current_redis", lambda: _R())
    monkeypatch.setattr(scheduler, "compute_market", fake_compute)
    monkeypatch.setattr(settings, "SIGNAL_RADAR_PREWARM_BROAD_ENABLED", False)
    asyncio.run(scheduler._prewarm_once())
    assert order[:3] == ["cn:star50", "hk:hstech", "us:nasdaq100"]


class TestCompositeRanking:
    """入榜 = 综合分（类型确认程度 + 强弱 + 新鲜度，最新一天再加共振）+ 每类保底名额。"""

    def test_fresh_signal_beats_stale_one(self):
        """同类型：今天刚出现的中等信号，排在 25 天前的强信号前面（用户最关心新信号）。"""
        stale = _raw("OLD", "2026-08-25", "buy", 0.8, level=2)
        fresh = _raw("NEW", "2026-09-18", "buy", 0.55, level=2)
        days = build_days([[stale], [fresh]], ["2026-09-19"], top_n=1)
        assert [s.symbol for s in days[0].signals] == ["NEW"]

    def test_each_level_keeps_two_slots_then_by_score(self):
        """每类最多保底 2 个名额，其余按综合分：弱一类不能靠轮流挤掉强三类。"""
        histories = (
            [[_raw(f"L3-{i}", "2026-09-19", "buy", 0.8, level=3)] for i in range(8)]
            + [[_raw(f"L1-{i}", "2026-09-19", "buy", 0.35, level=1)] for i in range(4)]
        )
        days = build_days(histories, ["2026-09-19"], top_n=6)
        syms = [s.symbol for s in days[0].signals]
        assert sum(s.startswith("L1") for s in syms) == 2, "一类保底 2 个，不再轮流占到一半"
        assert sum(s.startswith("L3") for s in syms) == 4

    def test_resonance_bonus_reranks_latest_day(self):
        """最新一天：候选池里共振的信号加分，可以挤进前 N。"""
        from app.schemas.signal_radar import RadarDayOut, RadarSignalOut

        def sig(sym, strength, verdict=None):
            return RadarSignalOut(symbol=sym, name=sym, side="buy", label="二买", signal_type="buy2",
                                  date="2026-09-19", price=1.0, strength=strength, bias="bullish",
                                  signal_strength="medium", confirmed=True, pivot_stage_depth=0.5,
                                  sub_level_verdict=verdict)
        day = RadarDayOut(date="2026-09-19", buy_count=3, sell_count=0,
                          signals=[sig("A", 0.8), sig("B", 0.7), sig("C", 0.55, "resonance_buy")])
        out = svc.rerank_with_resonance(day, top_n=2)
        assert [s.symbol for s in out.signals] == ["C", "A"]
        assert out.buy_count == 2
