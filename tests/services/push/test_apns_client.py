"""apns_client：验证真的调用了 aioapns 客户端上存在的方法（send_notification）。"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.push import apns_client


class _FakeClient:
    def __init__(self, send_notification: AsyncMock) -> None:
        self.send_notification = send_notification


@pytest.mark.asyncio
async def test_send_calls_send_notification_and_returns_success():
    fake_result = type("Result", (), {"is_successful": True, "description": ""})()
    fake_client = _FakeClient(AsyncMock(return_value=fake_result))

    with patch.object(apns_client, "get_client", return_value=fake_client):
        ok = await apns_client.send("tok", "title", "body", {"market": "us"})

    assert ok is True
    fake_client.send_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_returns_false_on_rejection():
    fake_result = type("Result", (), {"is_successful": False, "description": "BadDeviceToken"})()
    fake_client = _FakeClient(AsyncMock(return_value=fake_result))

    with patch.object(apns_client, "get_client", return_value=fake_client):
        ok = await apns_client.send("tok", "title", "body")

    assert ok is False


@pytest.mark.asyncio
async def test_send_returns_false_and_does_not_raise_on_client_error():
    fake_client = _FakeClient(AsyncMock(side_effect=RuntimeError("boom")))

    with patch.object(apns_client, "get_client", return_value=fake_client):
        ok = await apns_client.send("tok", "title", "body")

    assert ok is False


def test_client_recreated_for_each_task_event_loop():
    """同一循环复用连接，下一次 Celery asyncio.run 必须新建客户端。"""
    async def get_twice():
        first = apns_client.get_client()
        assert apns_client.get_client() is first
        return first

    with patch.object(apns_client, "APNs", side_effect=[object(), object()]) as factory:
        first = asyncio.run(get_twice())
        second = asyncio.run(get_twice())
    assert first is not second
    assert factory.call_count == 2
