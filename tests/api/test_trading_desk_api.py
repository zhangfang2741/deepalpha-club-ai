"""交易台 API 端到端测试：用 MockEngine + Redis 替身，不碰真实 LLM 与真实 Redis。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.trading_desk import get_engine, router
from app.cache.client import get_redis
from app.services.trading_desk.engines.mock import MockEngine
from tests.services.trading_desk.test_runner import FakeRedisAll


@pytest.fixture
def redis() -> FakeRedisAll:
    return FakeRedisAll()


@pytest.fixture
def app(redis: FakeRedisAll) -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api/v1/trading-desk")
    application.dependency_overrides[get_redis] = lambda: redis
    application.dependency_overrides[get_current_user] = lambda: object()
    application.dependency_overrides[get_engine] = lambda: MockEngine(tick_seconds=0)
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _create_run(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/trading-desk/runs", json={"ticker": "NVDA"})
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


def _parse_sse(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


async def test_create_run_returns_run_id(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    assert len(run_id) == 32


async def test_create_run_rejects_empty_ticker(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/trading-desk/runs", json={"ticker": ""})

    assert resp.status_code == 422


async def test_create_run_uppercases_ticker(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/trading-desk/runs", json={"ticker": " nvda "})
    run_id = resp.json()["run_id"]

    async with client.stream("GET", f"/api/v1/trading-desk/runs/{run_id}/stream") as stream:
        body = "".join([chunk async for chunk in stream.aiter_text()])

    assert _parse_sse(body)[0]["data"]["ticker"] == "NVDA"


async def test_stream_delivers_full_event_sequence(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    async with client.stream("GET", f"/api/v1/trading-desk/runs/{run_id}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in resp.aiter_text()])

    types = [e["type"] for e in _parse_sse(body)]

    assert types[0] == "run.started"
    assert types[-1] == "run.finished"
    assert "agent.token" in types
    assert "debate.turn" in types
    assert "verdict" in types


async def test_stream_emits_sse_ids_for_reconnect(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    async with client.stream("GET", f"/api/v1/trading-desk/runs/{run_id}/stream") as resp:
        body = "".join([chunk async for chunk in resp.aiter_text()])

    id_lines = [line for line in body.splitlines() if line.startswith("id: ")]

    assert len(id_lines) > 1
    assert len(id_lines) == len(_parse_sse(body))


async def test_stream_resumes_from_last_event_id(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    async with client.stream("GET", f"/api/v1/trading-desk/runs/{run_id}/stream") as resp:
        full = "".join([chunk async for chunk in resp.aiter_text()])

    all_ids = [line[4:] for line in full.splitlines() if line.startswith("id: ")]
    resume_from = all_ids[2]

    async with client.stream(
        "GET",
        f"/api/v1/trading-desk/runs/{run_id}/stream",
        headers={"Last-Event-ID": resume_from},
    ) as resp:
        partial = "".join([chunk async for chunk in resp.aiter_text()])

    resumed_ids = [line[4:] for line in partial.splitlines() if line.startswith("id: ")]

    assert resume_from not in resumed_ids, "断线重连不应重发已收到的那一条"
    assert resumed_ids == all_ids[3:]


async def test_inject_requires_text(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    resp = await client.post(f"/api/v1/trading-desk/runs/{run_id}/control", json={"action": "inject"})

    assert resp.status_code == 422


async def test_inject_rejects_blank_text(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    resp = await client.post(
        f"/api/v1/trading-desk/runs/{run_id}/control", json={"action": "inject", "text": "   "}
    )

    assert resp.status_code == 422


async def test_control_actions_are_accepted(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    for payload in (
        {"action": "pause"},
        {"action": "inject", "text": "把出口管制风险的权重调高"},
        {"action": "resume"},
        {"action": "cancel"},
    ):
        resp = await client.post(f"/api/v1/trading-desk/runs/{run_id}/control", json=payload)
        assert resp.status_code == 200, payload
        assert resp.json()["accepted"] is True


async def test_unknown_control_action_is_rejected(client: AsyncClient) -> None:
    run_id = await _create_run(client)

    resp = await client.post(f"/api/v1/trading-desk/runs/{run_id}/control", json={"action": "explode"})

    assert resp.status_code == 422
