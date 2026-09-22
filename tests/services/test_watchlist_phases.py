"""自选股阶段标签服务测试。

用 monkeypatch 替换 fetch_kline，不打真实行情源；缠论分析本身跑真实
ChanAnalyzer（快、无 IO），验证批量并发、单只失败不影响其他标的、
取不到阶段时返回 None 这几件事。
"""
from __future__ import annotations

import pytest

from app.services import watchlist_phases as svc


def _bars(n: int = 60, start: float = 100.0) -> list[dict]:
    """造一段简单交替涨跌的日线，保证能形成笔（不追求形成中枢）。"""
    bars = []
    price = start
    for i in range(n):
        delta = 3 if i % 2 == 0 else -2
        price += delta
        bars.append({
            "time": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": price - delta, "high": price + 1, "low": price - 1,
            "close": price, "volume": 1000,
        })
    return bars


class _FakeRedis:
    """占位：fetch_kline 已被整体替换，这里只是满足类型签名，不会被真正调用。"""


@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


async def test_returns_empty_list_for_no_items(fake_redis):
    result = await svc.fetch_phase_labels([], user_id=1, redis=fake_redis)
    assert result == []


async def test_single_symbol_success(monkeypatch, fake_redis):
    async def fake_fetch_kline(*, user_id, symbol, start_date, end_date, freq, redis):
        return _bars()

    monkeypatch.setattr(svc, "fetch_kline", fake_fetch_kline)
    result = await svc.fetch_phase_labels([("us", "AAPL")], user_id=1, redis=fake_redis)
    assert len(result) == 1
    assert result[0].market == "us"
    assert result[0].symbol == "AAPL"
    # 结构是否成形取决于合成数据能不能凑出中枢，不强断言具体 phase，
    # 只断言字段类型一致（要么两者都是 None，要么两者都不是）。
    assert (result[0].phase is None) == (result[0].phase_label is None)


async def test_kline_failure_for_one_symbol_does_not_affect_others(monkeypatch, fake_redis):
    async def fake_fetch_kline(*, user_id, symbol, start_date, end_date, freq, redis):
        if symbol == "BAD":
            raise RuntimeError("行情源挂了")
        return _bars()

    monkeypatch.setattr(svc, "fetch_kline", fake_fetch_kline)
    result = await svc.fetch_phase_labels(
        [("us", "BAD"), ("us", "GOOD")], user_id=1, redis=fake_redis,
    )
    by_symbol = {r.symbol: r for r in result}
    assert by_symbol["BAD"].phase is None
    assert by_symbol["BAD"].phase_label is None
    # GOOD 那只不受 BAD 失败影响，照样跑完（是否有阶段取决于合成数据，不强断言）
    assert "GOOD" in by_symbol


async def test_empty_bars_yields_none_phase(monkeypatch, fake_redis):
    async def fake_fetch_kline(*, user_id, symbol, start_date, end_date, freq, redis):
        return []

    monkeypatch.setattr(svc, "fetch_kline", fake_fetch_kline)
    result = await svc.fetch_phase_labels([("us", "X")], user_id=1, redis=fake_redis)
    assert result[0].phase is None
    assert result[0].phase_label is None


async def test_concurrent_scan_covers_all_requested_symbols(monkeypatch, fake_redis):
    async def fake_fetch_kline(*, user_id, symbol, start_date, end_date, freq, redis):
        return _bars()

    monkeypatch.setattr(svc, "fetch_kline", fake_fetch_kline)
    items = [("us", f"SYM{i}") for i in range(20)]  # 超过并发上限，验证 semaphore 不丢标的
    result = await svc.fetch_phase_labels(items, user_id=1, redis=fake_redis)
    assert {r.symbol for r in result} == {f"SYM{i}" for i in range(20)}
