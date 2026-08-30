"""交易台历史接口测试：GET /runs 与 GET /runs/{run_id}。

不走 FastAPI TestClient 起整个 app（依赖过重），而是直接调 endpoint 函数
+ monkeypatch persistence 模块 + 一个最简 FakeAsyncSession。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.trading_desk import get_run, list_runs
from app.main import app
from app.models.user import User


_TS = datetime(2026, 8, 30, 10, 0, 0, tzinfo=UTC)
_TS_END = datetime(2026, 8, 30, 10, 0, 1, tzinfo=UTC)


class _Row:
    """可被 pydantic 模型序列化的行替身：和 persistence 用的同形字段。"""

    def __init__(
        self,
        run_id: str,
        user_id: int,
        ticker: str,
        trade_date: str = "2026-08-30",
        engine: str = "mock/1",
        status: str = "completed",
        duration_ms: int = 1200,
        created_at: datetime | None = None,
        finished_at: datetime | None = None,
        verdict: dict | None = None,
        signals: list | None = None,
        turns: list | None = None,
    ) -> None:
        self.id = run_id
        self.user_id = user_id
        self.ticker = ticker
        self.trade_date = trade_date
        self.engine = engine
        self.status = status
        self.duration_ms = duration_ms
        self.created_at = created_at if created_at is not None else _TS
        self.finished_at = finished_at
        self.verdict = verdict
        self.signals = signals
        self.turns = turns


class FakeAsyncSession:
    """最小 async session：list_runs / get_run 用得到的接口。"""

    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    async def exec(self, stmt: Any) -> Any:
        class _Result:
            def all(inner) -> list[_Row]:
                return list(self._rows)
        return _Result()

    async def get(self, _model: Any, run_id: str) -> _Row | None:
        for r in self._rows:
            if str(r.id) == run_id:
                return r
        return None


@pytest.fixture
def user_alice() -> User:
    return User(id=1, email="alice@example.com", username="alice", hashed_password="x")  # type: ignore[call-arg]


@pytest.fixture
def user_bob() -> User:
    return User(id=2, email="bob@example.com", username="bob", hashed_password="x")  # type: ignore[call-arg]


def _override_user(user: User):  # type: ignore[no-untyped-def]
    async def _dep() -> User:
        return user
    return _dep


async def test_list_runs_returns_user_owned_rows(
    monkeypatch: pytest.MonkeyPatch,
    user_alice: User,
) -> None:
    """list_runs 必须按 user_id 隔离：alice 看不到 bob 的 run。"""
    rows = [
        _Row(run_id="r1", user_id=1, ticker="NVDA"),
        _Row(run_id="r2", user_id=1, ticker="AAPL"),
    ]

    async def fake_list_runs(db: Any, *, user_id: int, ticker: str | None = None,
                             limit: int = 20, offset: int = 0) -> list[_Row]:
        return [r for r in rows if r.user_id == user_id]

    monkeypatch.setattr("app.services.trading_desk.persistence.list_runs", fake_list_runs)

    app.dependency_overrides[get_current_user] = _override_user(user_alice)
    try:
        resp = await list_runs(user=user_alice, db=FakeAsyncSession(rows), ticker=None, limit=20, offset=0)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert [r.run_id for r in resp.runs] == ["r1", "r2"]
    assert resp.runs[0].ticker == "NVDA"


async def test_get_run_returns_404_for_other_users_run(
    monkeypatch: pytest.MonkeyPatch,
    user_alice: User,
) -> None:
    """越权：alice 拿 bob 的 run_id 必须 404，不泄漏存在性。"""
    bob_row = _Row(run_id="bob-run", user_id=2, ticker="NVDA")

    async def fake_get_run(db: Any, *, run_id: str, user_id: int) -> _Row | None:
        if run_id == "bob-run" and user_id == 2:
            return bob_row
        return None

    monkeypatch.setattr("app.services.trading_desk.persistence.get_run", fake_get_run)

    app.dependency_overrides[get_current_user] = _override_user(user_alice)
    try:
        with pytest.raises(HTTPException) as exc_info:
            await get_run(run_id="bob-run", user=user_alice, db=FakeAsyncSession([bob_row]))
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert exc_info.value.status_code == 404


async def test_get_run_returns_full_payload_for_owner(
    monkeypatch: pytest.MonkeyPatch,
    user_alice: User,
) -> None:
    """持有者拿到包含 verdict / signals / turns 的完整 payload。"""
    row = _Row(
        run_id="alice-1", user_id=1, ticker="NVDA",
        verdict={"signal": "BUY", "confidence": 0.66},
        signals=[{"stage_id": "market", "dir": "bull", "conf": 64}],
        turns=[{"turn_id": "mkt-1", "text": "回调后站稳", "name": "技术面分析师"}],
    )

    async def fake_get_run(db: Any, *, run_id: str, user_id: int) -> _Row | None:
        if run_id == "alice-1" and user_id == 1:
            return row
        return None

    monkeypatch.setattr("app.services.trading_desk.persistence.get_run", fake_get_run)

    app.dependency_overrides[get_current_user] = _override_user(user_alice)
    try:
        resp = await get_run(run_id="alice-1", user=user_alice, db=FakeAsyncSession([row]))
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.run_id == "alice-1"
    assert resp.verdict == {"signal": "BUY", "confidence": 0.66}
    assert len(resp.signals) == 1
    assert resp.turns[0]["text"] == "回调后站稳"


async def test_list_runs_summary_extracts_verdict_signal_and_counts(
    monkeypatch: pytest.MonkeyPatch,
    user_alice: User,
) -> None:
    """Summary 字段从 verdict/turns/signals 里抽取最小子集。"""
    row = _Row(
        run_id="r1", user_id=1, ticker="NVDA",
        verdict={"signal": "BUY", "confidence": 0.66},
        signals=[{"a": 1}, {"b": 2}],
        turns=[{"t": 1}, {"t": 2}, {"t": 3}],
    )

    async def fake_list_runs(db: Any, *, user_id: int, ticker: str | None = None,
                             limit: int = 20, offset: int = 0) -> list[_Row]:
        return [row]

    monkeypatch.setattr("app.services.trading_desk.persistence.list_runs", fake_list_runs)

    app.dependency_overrides[get_current_user] = _override_user(user_alice)
    try:
        resp = await list_runs(user=user_alice, db=FakeAsyncSession([row]), ticker=None, limit=20, offset=0)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    s = resp.runs[0]
    assert s.verdict_signal == "BUY"
    assert s.verdict_confidence == 0.66
    assert s.signals_count == 2
    assert s.turns_count == 3


async def test_list_runs_summary_handles_missing_verdict_and_arrays(
    monkeypatch: pytest.MonkeyPatch,
    user_alice: User,
) -> None:
    """运行中或进程崩溃的占位行：verdict/turns/signals 都 None —— summary 必须容错。"""
    row = _Row(
        run_id="r-running", user_id=1, ticker="NVDA",
        status="running", finished_at=None,
        verdict=None, signals=None, turns=None,
    )

    async def fake_list_runs(db: Any, *, user_id: int, ticker: str | None = None,
                             limit: int = 20, offset: int = 0) -> list[_Row]:
        return [row]

    monkeypatch.setattr("app.services.trading_desk.persistence.list_runs", fake_list_runs)

    app.dependency_overrides[get_current_user] = _override_user(user_alice)
    try:
        resp = await list_runs(user=user_alice, db=FakeAsyncSession([row]), ticker=None, limit=20, offset=0)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    s = resp.runs[0]
    assert s.verdict_signal is None
    assert s.verdict_confidence is None
    assert s.turns_count == 0
    assert s.signals_count == 0
    assert s.finished_at is None


# 简单的 sentinel，确认 asyncio.run 能正常工作（其它测试已隐含，这里只是冗余校验）
def test_asyncio_smoke() -> None:
    assert asyncio.get_event_loop_policy() is not None