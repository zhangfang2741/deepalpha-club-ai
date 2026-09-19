"""自选股 API：列表 / 加入（含幂等更新名称）/ 删除（含 404）。"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.watchlist import router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router, prefix="/watchlist")
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": 1})()
    yield TestClient(app)


def _item(market="us", symbol="AAPL", name="苹果"):
    return type("Item", (), {
        "market": market, "symbol": symbol, "name": name,
        "created_at": datetime(2026, 9, 19, tzinfo=UTC),
    })()


def test_list_watchlist_returns_items(client):
    from app.services import watchlist as store

    with patch.object(store, "list_items", AsyncMock(return_value=[_item()])):
        resp = client.get("/watchlist")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["symbol"] == "AAPL"


def test_add_to_watchlist(client):
    from app.services import watchlist as store

    with patch.object(store, "add_item", AsyncMock(return_value=_item())) as mock_add:
        resp = client.post("/watchlist", json={"market": "us", "symbol": "aapl", "name": "苹果"})
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "AAPL"
    mock_add.assert_awaited_once()
    # user_id 来自 get_current_user 覆写（1），不是请求体里的字段
    assert mock_add.await_args is not None
    assert mock_add.await_args.args[1] == 1


def test_add_rejects_unknown_market(client):
    resp = client.post("/watchlist", json={"market": "jp", "symbol": "7203", "name": "丰田"})
    assert resp.status_code == 422


def test_remove_from_watchlist_success(client):
    from app.services import watchlist as store

    with patch.object(store, "remove_item", AsyncMock(return_value=True)):
        resp = client.delete("/watchlist/us/AAPL")
    assert resp.status_code == 200
    assert resp.json() == {"removed": True}


def test_remove_from_watchlist_not_found(client):
    from app.services import watchlist as store

    with patch.object(store, "remove_item", AsyncMock(return_value=False)):
        resp = client.delete("/watchlist/us/AAPL")
    assert resp.status_code == 404
