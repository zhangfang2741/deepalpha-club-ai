"""联系我们接口测试：SMTP 全部 mock。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth.dependencies import get_current_user
from app.core.config import settings
from app.main import app
from app.services import email as email_service


@pytest.fixture
def client():
    user = MagicMock(id=7, email="u@example.com", phone=None)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


def test_feedback_sends_email(client):
    with patch.object(settings, "FEEDBACK_TO_EMAIL", "ops@example.com"), patch.object(
        email_service, "is_configured", return_value=True
    ), patch.object(email_service, "send_email", AsyncMock()) as send:
        r = client.post("/api/v1/feedback", json={"content": "建议加个功能 <b>"})
    assert r.status_code == 200
    to, subject, html_body, text = send.call_args.args[:4]
    assert to == "ops@example.com"
    assert "u@example.com" in subject
    assert "&lt;b&gt;" in html_body and "建议加个功能" in text


def test_feedback_rejects_blank(client):
    r = client.post("/api/v1/feedback", json={"content": "   "})
    assert r.status_code == 422


def test_feedback_503_when_unconfigured(client):
    with patch.object(settings, "FEEDBACK_TO_EMAIL", ""):
        r = client.post("/api/v1/feedback", json={"content": "hi"})
    assert r.status_code == 503
