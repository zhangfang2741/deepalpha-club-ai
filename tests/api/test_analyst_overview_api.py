"""分析师评级概览接口：鉴权后返回、非美股不支持、参数校验。"""

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import analyst_upgrade as api_mod
from app.api.v1.auth import get_current_user
from app.main import app
from app.schemas.analyst_upgrade import AnalystOverviewOut


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": 1})()

    async def fake(symbol, lang, *, redis):
        return AnalystOverviewOut(symbol=symbol.upper(), status="ok", note="n")

    monkeypatch.setattr(api_mod, "get_analyst_overview", fake)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_overview_ok(client):
    body = client.get("/api/v1/analyst-upgrades/overview/nvda").json()
    assert body["symbol"] == "NVDA" and body["status"] == "ok"


def test_overview_non_us_unsupported(client):
    body = client.get("/api/v1/analyst-upgrades/overview/0700?market=hk").json()
    assert body["status"] == "unsupported_market"


def test_overview_bad_params(client):
    assert client.get("/api/v1/analyst-upgrades/overview/NVDA?lang=fr").status_code == 422
    assert client.get("/api/v1/analyst-upgrades/overview/NVDA?market=jp").status_code == 422
