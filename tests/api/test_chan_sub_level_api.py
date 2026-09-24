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
