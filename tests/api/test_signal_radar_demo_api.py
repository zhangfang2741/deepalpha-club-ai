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

    async def set(self, k, v, ex=None, keepttl=False, nx=False):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

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
        market="us", universe="sp500", etf_name="标普500", universe_size=100,
        as_of=target, top_n=10, days=[], status="ready",
    )
    redis.store[svc._demo_cache_key("us", "sp500", target)] = cached.model_dump_json()
    body = client.get("/signal-radar/demo", params={"market": "us"}).json()
    assert body["status"] == "ready"
    assert body["as_of"] == target
    assert spawned == []


# ---- 按 universe 区分：同一市场下切换纳斯达克100 / 标普500，示例日应是各自指数的快照 ----

@pytest.fixture()
def recorded(monkeypatch, ctx):
    calls = []

    async def _noop():
        return None

    def fake_scan(market, universe_key, mode=None):
        # 创建协程时就记下参数（_spawn 会直接关掉协程，函数体不会执行）
        calls.append((market, universe_key))
        return _noop()

    monkeypatch.setattr(api, "_run_demo_scan", fake_scan)
    return calls


def test_universe_param_scans_that_universe(ctx, recorded):
    client, _, spawned = ctx
    body = client.get("/signal-radar/demo", params={"market": "us", "universe": "sp500"}).json()
    assert body["status"] == "generating"
    assert body["universe"] == "sp500"
    assert len(spawned) == 1
    assert recorded == [("us", "sp500")]


def test_missing_universe_uses_market_default(ctx):
    client, _, _ = ctx
    body = client.get("/signal-radar/demo", params={"market": "us"}).json()
    assert body["universe"] == "sp500"


def test_cache_is_per_universe(ctx):
    client, redis, spawned = ctx
    target = svc.demo_snapshot_date()
    cached = svc.SignalRadarResponse(
        market="us", universe="nasdaq100", etf_name="纳斯达克100", universe_size=100,
        as_of=target, top_n=10, days=[], status="ready",
    )
    redis.store[svc._demo_cache_key("us", "nasdaq100", target)] = cached.model_dump_json()
    hit = client.get("/signal-radar/demo", params={"market": "us", "universe": "nasdaq100"}).json()
    assert hit["status"] == "ready" and spawned == []
    miss = client.get("/signal-radar/demo", params={"market": "us", "universe": "sp500"}).json()
    assert miss["status"] == "generating"
    assert miss["universe"] == "sp500"
    assert len(spawned) == 1


def test_generating_dedup_is_per_universe(ctx):
    client, _, spawned = ctx
    client.get("/signal-radar/demo", params={"market": "us", "universe": "nasdaq100"})
    client.get("/signal-radar/demo", params={"market": "us", "universe": "sp500"})
    client.get("/signal-radar/demo", params={"market": "us", "universe": "sp500"})
    assert len(spawned) == 2


def test_unknown_universe_rejected(ctx):
    client, _, spawned = ctx
    resp = client.get("/signal-radar/demo", params={"market": "us", "universe": "hsi"})
    assert resp.status_code == 400
    assert spawned == []


# ---- scope：新版 App 拿全部在场信号（按出现时间排），旧版 App 仍截取前 N ----

def _snapshot_with(n: int) -> svc.SignalRadarResponse:
    from app.schemas.signal_radar import RadarDayOut, RadarSignalOut

    signals = [RadarSignalOut(symbol=f"S{i:02d}", name=f"S{i:02d}", side="buy", label="二买", signal_type="buy2",
                              date="2026-09-30", price=1.0, strength=0.5, bias="bullish",
                              signal_strength="medium", confirmed=True, pivot_stage_depth=0.5, age_days=0)
               for i in range(n)]
    day = RadarDayOut(date="2026-09-30", buy_count=n, sell_count=0, signals=signals)
    return svc.SignalRadarResponse(market="us", universe="nasdaq100", etf_name="纳斯达克100", universe_size=100,
                                   as_of="2026-09-30", top_n=10, days=[day], status="ready")


def test_scope_all_returns_every_signal_default_keeps_top_n(ctx):
    client, redis, _ = ctx
    redis.store[svc._demo_cache_key("us", "sp500", svc.demo_snapshot_date())] = \
        _snapshot_with(25).model_dump_json()
    full = client.get("/signal-radar/demo", params={"market": "us", "scope": "all"}).json()
    legacy = client.get("/signal-radar/demo", params={"market": "us"}).json()
    assert len(full["days"][0]["signals"]) == 25
    assert len(legacy["days"][0]["signals"]) == svc.DEFAULT_TOP_N
    assert legacy["days"][0]["buy_count"] == svc.DEFAULT_TOP_N


def test_scope_rejects_unknown_value(ctx):
    client, _, _ = ctx
    assert client.get("/signal-radar/demo", params={"market": "us", "scope": "best"}).status_code == 422
