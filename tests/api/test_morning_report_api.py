"""晨报 API：当日命中 / 生成中 / 回退最近一期 / dates / token 注册。"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.morning_report import router
from tests.services.morning_report.test_schema import _valid_content


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    # dependency_overrides 的 key 必须是路由 Depends() 里绑定的那个函数对象本身
    # （在装饰路由时就已固化的引用）。若在 patch() 生效之后才通过模块属性取值，
    # 拿到的会是 patch 换上去的替身，反而对不上，导致 override 失效——所以这里
    # 先在 patch 之前取出真身用于 override，patch 本身作为兜底/冗余保留即可。
    real_get_current_user = __import__(
        "app.api.v1.morning_report", fromlist=["get_current_user"]
    ).get_current_user
    app.dependency_overrides[real_get_current_user] = lambda: type("U", (), {"id": 1})()
    with patch("app.api.v1.morning_report.get_current_user", lambda: type("U", (), {"id": 1})()):
        yield TestClient(app)


def test_get_report_success(client):
    from app.services.morning_report import store

    record = type("R", (), {
        "market": "us", "trade_date": date(2026, 9, 8), "status": "success",
        "content": _valid_content(),
    })()
    with patch.object(store, "get_report", AsyncMock(return_value=(record, False))):
        resp = client.get("/?market=us")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["status"] == "success" and body["meta"]["stale"] is False
    assert body["content"]["headline"]["zh"]


def test_get_report_generating_returns_empty_content(client):
    from app.services.morning_report import store

    record = type("R", (), {
        "market": "us", "trade_date": date(2026, 9, 8), "status": "generating", "content": {},
    })()
    with patch.object(store, "get_report", AsyncMock(return_value=(record, False))):
        resp = client.get("/?market=us")
    assert resp.json()["meta"]["status"] == "generating"
    assert resp.json()["content"] is None


def test_get_report_stale_fallback(client):
    from app.services.morning_report import store

    record = type("R", (), {
        "market": "us", "trade_date": date(2026, 9, 7), "status": "success",
        "content": _valid_content(),
    })()
    with patch.object(store, "get_report", AsyncMock(return_value=(record, True))):
        resp = client.get("/?market=us")
    assert resp.json()["meta"]["stale"] is True


def test_dates(client):
    from app.services.morning_report import store

    with patch.object(store, "list_dates", AsyncMock(return_value=[date(2026, 9, 8), date(2026, 9, 7)])):
        resp = client.get("/dates?market=us")
    assert resp.json()["dates"] == ["2026-09-08", "2026-09-07"]


def test_register_token(client):
    from app.services.morning_report import store

    with patch.object(store, "upsert_token", AsyncMock()) as m:
        resp = client.post("/device-token", json={"token": "abc123", "locale": "en"})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    m.assert_awaited_once()
