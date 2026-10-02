"""雷达按行业：一次取回某天全部行业池（App 行业筛选条用）。"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import signal_radar as api
from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.schemas.signal_radar import RadarSignalOut
from app.services.signal_radar import sectors
from app.services.signal_radar import service as svc


class _Redis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v


@pytest.fixture()
def ctx():
    app = FastAPI()
    app.include_router(api.router, prefix="/signal-radar")
    redis = _Redis()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app), redis


async def test_sector_pools_for_current_universe(ctx):
    client, redis = ctx
    sig = RadarSignalOut(symbol="NVDA", name="英伟达", side="buy", label="一买", signal_type="buy1",
                         date="2026-09-30", price=1.0, strength=0.5, bias="bullish", signal_strength="medium",
                         confirmed=True, pivot_stage_depth=0.5, sector="technology")
    await sectors.write_pools(redis, svc._mode_ns("loose"), "us", "nasdaq100",
                              {"2026-09-30": {"technology": [sig]}}, ttl=60)
    body = client.get("/signal-radar/sector-pools",
                      params={"market": "us", "universe": "nasdaq100", "date": "2026-09-30"}).json()
    assert body["available"] is True and body["universe"] == "nasdaq100"
    assert [s["symbol"] for s in body["sectors"]["technology"]] == ["NVDA"]
    empty = client.get("/signal-radar/sector-pools",
                       params={"market": "us", "universe": "nasdaq100", "date": "2026-09-29"}).json()
    assert empty["available"] is False and empty["sectors"] == {}


def test_sector_pools_rejects_unknown_universe(ctx):
    client, _ = ctx
    resp = client.get("/signal-radar/sector-pools", params={"market": "us", "universe": "nope", "date": "2026-09-30"})
    assert resp.status_code == 400
