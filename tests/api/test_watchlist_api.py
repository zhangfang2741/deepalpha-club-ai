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


@pytest.fixture(autouse=True)
def _no_sample_seeding():
    """列表接口首次会补示例自选（写库）；这些用例只测接口本身，统一替掉。"""
    from app.services import watchlist as store

    with patch.object(store, "ensure_samples", AsyncMock()) as m:
        yield m


def _item(market="us", symbol="AAPL", name="苹果", is_sample=False):
    return type("Item", (), {
        "market": market, "symbol": symbol, "name": name, "is_sample": is_sample,
        "created_at": datetime(2026, 9, 19, tzinfo=UTC),
    })()


def test_list_seeds_samples_and_marks_them(client, _no_sample_seeding):
    from app.services import watchlist as store

    items = [_item("us", "NVDA", "英伟达", is_sample=True), _item()]
    with patch.object(store, "list_items", AsyncMock(return_value=items)):
        body = client.get("/watchlist").json()
    _no_sample_seeding.assert_awaited_once()
    assert [i["is_sample"] for i in body["items"]] == [True, False]


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


def test_add_rejects_when_watchlist_full(client):
    from app.services import watchlist as store

    with patch.object(store, "add_item", AsyncMock(side_effect=store.WatchlistLimitExceeded(1))):
        resp = client.post("/watchlist", json={"market": "us", "symbol": "AAPL", "name": "苹果"})
    assert resp.status_code == 400
    assert "1" in resp.json()["detail"]


def test_list_watchlist_reports_max_items_for_default_free_tier(client):
    from app.services import watchlist as store

    with patch.object(store, "list_items", AsyncMock(return_value=[_item()])):
        resp = client.get("/watchlist")
    assert resp.json()["max_items"] == store.TIER_LIMITS["free"]


def test_list_watchlist_reports_max_items_for_basic_tier(client):
    from app.services import watchlist as store

    with patch.object(store, "list_items", AsyncMock(return_value=[_item()])):
        resp = client.get("/watchlist", params={"tier": "basic"})
    assert resp.json()["max_items"] == store.TIER_LIMITS["basic"]


def test_list_watchlist_reports_unlimited_for_premium_tier(client):
    from app.services import watchlist as store

    with patch.object(store, "list_items", AsyncMock(return_value=[_item()])):
        resp = client.get("/watchlist", params={"tier": "premium"})
    assert resp.json()["max_items"] is None


def test_add_to_watchlist_passes_tier_through(client):
    from app.services import watchlist as store

    with patch.object(store, "add_item", AsyncMock(return_value=_item())) as mock_add:
        resp = client.post(
            "/watchlist", params={"tier": "basic"},
            json={"market": "us", "symbol": "aapl", "name": "苹果"},
        )
    assert resp.status_code == 200
    assert mock_add.await_args.kwargs["tier"] == "basic"


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
