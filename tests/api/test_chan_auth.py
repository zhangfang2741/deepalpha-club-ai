"""缠论双通道认证端点测试。

SMTP 和阿里云都 mock 掉：本地没有凭据，而且测试不该真的发信发短信。
数据库层也 mock——这里测的是路由的编排逻辑（判别、验码、报错翻译），
不是 SQL。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.account import codes

EMAIL = "newuser@example.com"
PHONE_RAW = "13800138000"
PHONE_E164 = "+8613800138000"
STRONG_PASSWORD = "Abcd1234!"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def no_existing_user():
    """数据库里查不到任何用户。"""
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email", MagicMock(return_value=None)
    ), patch(
        "app.api.v1.auth.routes.database_service.get_user_by_phone", MagicMock(return_value=None)
    ):
        yield


def test_request_email_code_sends_code(client, no_existing_user):
    with patch.object(codes, "send_email_code", AsyncMock()) as send:
        resp = client.post("/api/v1/auth/register/request-code", json={"email": EMAIL})

    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert send.await_count == 1


def test_request_email_code_rejects_registered_email(client):
    existing = MagicMock(id=1, email=EMAIL)
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email",
        MagicMock(return_value=existing),
    ):
        resp = client.post("/api/v1/auth/register/request-code", json={"email": EMAIL})

    assert resp.status_code == 400


def test_request_email_code_returns_503_when_smtp_missing(client, no_existing_user):
    with patch.object(
        codes, "send_email_code", AsyncMock(side_effect=codes.CodeChannelUnavailableError)
    ):
        resp = client.post("/api/v1/auth/register/request-code", json={"email": EMAIL})

    assert resp.status_code == 503


def test_email_register_rejects_wrong_code(client, no_existing_user):
    with patch.object(
        codes, "verify_email_code", AsyncMock(side_effect=codes.CodeRejectedError)
    ):
        resp = client.post(
            "/api/v1/auth/register/verify",
            json={"email": EMAIL, "code": "000000", "password": STRONG_PASSWORD},
        )

    assert resp.status_code == 400


def test_email_register_creates_user_on_valid_code(client, no_existing_user):
    created = MagicMock(id=42, email=EMAIL, phone=None, username=None)
    with patch.object(codes, "verify_email_code", AsyncMock()), patch(
        "app.api.v1.auth.routes.database_service.create_user", MagicMock(return_value=created)
    ):
        resp = client.post(
            "/api/v1/auth/register/verify",
            json={"email": EMAIL, "code": "123456", "password": STRONG_PASSWORD},
        )

    assert resp.status_code == 200
    assert resp.json()["token"]["access_token"]


def test_email_register_rejects_weak_password(client, no_existing_user):
    resp = client.post(
        "/api/v1/auth/register/verify",
        json={"email": EMAIL, "code": "123456", "password": "weak"},
    )

    assert resp.status_code == 422


def test_password_reset_request_hides_whether_email_exists(client):
    """未注册的邮箱也返回成功，避免接口变成账号探测器。"""
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email", MagicMock(return_value=None)
    ), patch.object(codes, "send_email_code", AsyncMock()) as send:
        resp = client.post("/api/v1/auth/password-reset/request", json={"email": EMAIL})

    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert send.await_count == 0, "不该给未注册邮箱真的发信"
