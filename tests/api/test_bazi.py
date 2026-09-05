"""八字 API 端点测试。"""

from fastapi.testclient import TestClient

from app.main import app
from app.services.bazi import interpretation as interpretation_module

client = TestClient(app)


def test_get_bazi_chart_success():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "1990-05-15",
            "birth_time": "14:30:00",
            "birth_city": "北京",
            "gender": "male",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hour_known"] is True
    assert body["year_pillar"]["gan"] == "庚"
    assert body["year_pillar"]["zhi"] == "午"
    assert body["true_solar_time_applied"] is True


def test_get_bazi_chart_hour_unknown():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "1990-05-15",
            "birth_city": "北京",
            "gender": "female",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hour_known"] is False
    assert body["time_pillar"] is None


def test_get_bazi_chart_invalid_gender_returns_422():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "1990-05-15",
            "birth_city": "北京",
            "gender": "unknown",
        },
    )
    assert response.status_code == 422


def test_get_bazi_chart_invalid_date_returns_422():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "not-a-date",
            "birth_city": "北京",
            "gender": "male",
        },
    )
    assert response.status_code == 422


def test_get_bazi_interpretation_success(monkeypatch):
    class _FakeMessage:
        content = "今天适合签约 | 宜：签约 忌：争执"

    async def fake_call(messages, **kwargs):
        return _FakeMessage()

    monkeypatch.setattr(interpretation_module.llm_service, "call", fake_call)

    response = client.post(
        "/api/v1/bazi/interpretation",
        json={
            "birth_date": "1990-05-15",
            "birth_time": "14:30:00",
            "birth_city": "北京",
            "gender": "male",
            "section": "daily",
        },
    )
    assert response.status_code == 200
    assert response.json()["text"] == "今天适合签约 | 宜：签约 忌：争执"


def test_get_bazi_interpretation_invalid_section_returns_422():
    response = client.post(
        "/api/v1/bazi/interpretation",
        json={
            "birth_date": "1990-05-15",
            "birth_city": "北京",
            "gender": "male",
            "section": "not-a-section",
        },
    )
    assert response.status_code == 422
