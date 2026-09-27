"""信号雷达「自选」股票池接口：按当前用户该市场的自选股计算，缓存按用户隔离。"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import signal_radar as api
from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.db.session import get_db
from app.services.signal_radar import service as svc


class _Redis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None, keepttl=False, nx=False):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

    async def delete(self, k):
        self.store.pop(k, None)

    async def ttl(self, k):
        return -2


@pytest.fixture()
def ctx(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/signal-radar")
    redis = _Redis()
    items = []
    spawned = []
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_db] = lambda: None

    async def fake_list(db, user_id):
        return items

    monkeypatch.setattr(api, "list_items", fake_list)
    monkeypatch.setattr(api, "_spawn", lambda coro: (spawned.append(coro), coro.close()))
    return TestClient(app), redis, items, spawned


def _item(market, symbol, name):
    return SimpleNamespace(market=market, symbol=symbol, name=name)


def test_empty_watchlist_returns_ready_empty(ctx):
    client, _, items, spawned = ctx
    items.append(_item("hk", "0700", "腾讯控股"))  # 别的市场的不算
    body = client.get("/signal-radar", params={"market": "us", "universe": "watchlist"}).json()
    assert body["status"] == "ready" and body["universe"] == "watchlist"
    assert body["universe_size"] == 0 and body["days"] == []
    assert spawned == []


def test_cache_miss_spawns_scan_and_returns_generating(ctx):
    client, _, items, spawned = ctx
    items.extend([_item("us", "AAPL", "苹果"), _item("us", "TSLA", "特斯拉")])
    body = client.get("/signal-radar", params={"market": "us", "universe": "watchlist"}).json()
    assert body["status"] == "generating" and body["universe"] == "watchlist"
    assert len(spawned) == 1


def test_cache_hit_returns_user_result(ctx):
    client, redis, items, spawned = ctx
    items.append(_item("us", "AAPL", "苹果"))
    cached = svc.SignalRadarResponse(market="us", universe="watchlist", etf_name="自选", universe_size=1,
                                     as_of="2026-09-25", top_n=12, days=[], status="ready")
    redis.store[svc.watchlist_cache_key("us", 7, [("AAPL", "苹果")])] = cached.model_dump_json()
    body = client.get("/signal-radar", params={"market": "us", "universe": "watchlist"}).json()
    assert body["status"] == "ready" and body["universe_size"] == 1
    assert spawned == []


# ---- 并发：多人同时请求 / 刷新，同一份指数只跑一轮扫描 ----

def _snapshot(computed_at: str) -> str:
    from app.schemas.signal_radar import SignalRadarResponse
    return SignalRadarResponse(market="us", universe="nasdaq100", etf_name="纳斯达克100", universe_size=1,
                               as_of="2026-09-25", top_n=10, days=[], computed_at=computed_at).model_dump_json()


def test_concurrent_cold_requests_spawn_one_scan(ctx):
    client, _, _, spawned = ctx
    for _ in range(5):
        body = client.get("/signal-radar", params={"market": "us", "universe": "nasdaq100"}).json()
        assert body["status"] == "generating"
    assert len(spawned) == 1


def test_refresh_while_scanning_does_not_stack(ctx):
    client, _, _, spawned = ctx
    client.get("/signal-radar", params={"market": "us", "universe": "nasdaq100"})
    for _ in range(3):
        client.get("/signal-radar", params={"market": "us", "universe": "nasdaq100", "refresh": "true"})
    assert len(spawned) == 1, "扫描进行中再刷新只等这一轮，不再叠加"


def test_refresh_within_cooldown_uses_fresh_snapshot(ctx):
    from datetime import UTC, datetime, timedelta
    client, redis, _, spawned = ctx

    async def fresh_ttl(k):
        return svc._cache_ttl()  # 缓存本身不算陈旧，只看刷新冷却

    redis.ttl = fresh_ttl
    key = svc._cache_key("us", "nasdaq100")
    redis.store[key] = _snapshot(datetime.now(UTC).isoformat())
    client.get("/signal-radar", params={"market": "us", "universe": "nasdaq100", "refresh": "true"})
    assert spawned == [], "刚算过的快照，刷新不重扫"

    redis.store[key] = _snapshot((datetime.now(UTC) - timedelta(hours=1)).isoformat())
    client.get("/signal-radar", params={"market": "us", "universe": "nasdaq100", "refresh": "true"})
    assert len(spawned) == 1
