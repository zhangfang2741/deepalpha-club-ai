"""次级别确认接口：日线 + 30 分钟联动；30 分钟失败时仍返回 200、结论为不可用。"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import chan as chan_api
from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.services.chan import sub_level_service
from tests.services.chan.test_czsc_adapter import _intraday_bars
from tests.services.chan.test_czsc_signals import _decaying_downtrend_bars


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(chan_api.router, prefix="/chan")
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": 1})()
    app.dependency_overrides[get_redis] = lambda: None
    yield TestClient(app)


_PARAMS = {"symbol": "AAPL", "start_date": "2025-03-01", "end_date": "2025-05-08"}


def test_sub_level_returns_verdict_with_recent_signals(client):
    with patch.object(chan_api, "fetch_kline", AsyncMock(return_value=_decaying_downtrend_bars())), \
         patch.object(sub_level_service, "fetch_kline", AsyncMock(return_value=_intraday_bars(days=16))):
        resp = client.get("/chan/sub-level", params=_PARAMS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["sub_freq"] == "30min"
    assert body["daily_bias"] in ("bullish", "bearish", "neutral")
    assert body["verdict"] in ("resonance_buy", "resonance_sell", "counter_trend", "waiting")
    assert isinstance(body["recent_signals"], list)
    assert body["verdict_label"] and body["detail"]


def test_sub_level_degrades_when_30min_unavailable(client):
    with patch.object(chan_api, "fetch_kline", AsyncMock(return_value=_decaying_downtrend_bars())), \
         patch.object(sub_level_service, "fetch_kline", AsyncMock(side_effect=ValueError("限流"))):
        resp = client.get("/chan/sub-level", params=_PARAMS)
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "unavailable"


def test_sub_level_404_when_no_daily_bars(client):
    with patch.object(chan_api, "fetch_kline", AsyncMock(return_value=[])):
        resp = client.get("/chan/sub-level", params=_PARAMS)
    assert resp.status_code == 404


def test_sub_level_weekly_parent_pairs_with_daily(client):
    """周线详情页的次级别是日线（不跨级到 30 分钟）。"""
    parent = AsyncMock(return_value=_decaying_downtrend_bars())
    child = AsyncMock(return_value=_decaying_downtrend_bars())
    with patch.object(chan_api, "fetch_kline", parent), patch.object(sub_level_service, "fetch_kline", child):
        resp = client.get("/chan/sub-level", params={**_PARAMS, "parent_freq": "weekly"})
    assert resp.status_code == 200
    body = resp.json()
    assert (body["parent_freq"], body["sub_freq"]) == ("weekly", "daily")
    def freq_of(mock):
        args, kwargs = mock.call_args
        return kwargs.get("freq", args[4] if len(args) > 4 else None)

    assert freq_of(parent) == "weekly"
    assert freq_of(child) == "daily"


def test_sub_level_rejects_30min_parent(client):
    resp = client.get("/chan/sub-level", params={**_PARAMS, "parent_freq": "30min"})
    assert resp.status_code == 422
