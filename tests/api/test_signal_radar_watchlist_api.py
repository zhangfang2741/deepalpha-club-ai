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

    async def set(self, k, v, ex=None, keepttl=False):
        self.store[k] = v

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
