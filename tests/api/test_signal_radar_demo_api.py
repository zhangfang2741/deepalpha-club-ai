"""信号雷达「免费预览」接口：未订阅用户唯一能点开的一天（上个月 1 号）。"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import signal_radar as api
from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.services.signal_radar import service as svc


class _Redis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None, keepttl=False):
        self.store[k] = v

    async def delete(self, k):
        self.store.pop(k, None)


@pytest.fixture()
def ctx(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/signal-radar")
    redis = _Redis()
    spawned = []
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_redis] = lambda: redis
    monkeypatch.setattr(api, "_spawn", lambda coro: (spawned.append(coro), coro.close()))
    return TestClient(app), redis, spawned


def test_unsupported_market_rejected(ctx):
    client, _, spawned = ctx
    resp = client.get("/signal-radar/demo", params={"market": "jp"})
    assert resp.status_code == 400
    assert spawned == []


def test_cache_miss_spawns_scan_and_returns_generating(ctx):
    client, _, spawned = ctx
    body = client.get("/signal-radar/demo", params={"market": "us"}).json()
    assert body["status"] == "generating"
    assert body["market"] == "us"
    assert len(spawned) == 1


def test_cache_miss_does_not_spawn_twice_while_generating(ctx):
    client, _, spawned = ctx
    client.get("/signal-radar/demo", params={"market": "us"})
    client.get("/signal-radar/demo", params={"market": "us"})
    assert len(spawned) == 1


def test_cache_hit_returns_ready_snapshot_without_spawning(ctx):
    client, redis, spawned = ctx
    target = svc.demo_snapshot_date()
    cached = svc.SignalRadarResponse(
        market="us", universe="nasdaq100", etf_name="纳斯达克100", universe_size=100,
        as_of=target, top_n=10, days=[], status="ready",
    )
    redis.store[svc._demo_cache_key("us", target)] = cached.model_dump_json()
    body = client.get("/signal-radar/demo", params={"market": "us"}).json()
    assert body["status"] == "ready"
    assert body["as_of"] == target
    assert spawned == []
