"""量化研究接口：鉴权、参数校验、不支持市场、方法说明。"""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import quant_research as api_mod
from app.api.v1.auth import get_current_user
from app.main import app
from app.schemas.quant_research import QuantResearchOut
from tests.services.quant_research.fixtures import FIXTURE_DIR


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": 1})()
    golden = QuantResearchOut(**json.loads((FIXTURE_DIR / "golden_NVDA.json").read_text()))
    seen = {}

    async def fake(market, symbol, lang, *, redis):
        seen.update(market=market, symbol=symbol, lang=lang)
        if market.lower() != "us":
            from app.services.quant_research.builder import unsupported
            return unsupported(market, symbol, lang)
        return golden

    monkeypatch.setattr(api_mod, "get_quant_research", fake)
    yield TestClient(app), seen
    app.dependency_overrides.clear()


def test_get_quant_research_ok(client):
    c, seen = client
    r = c.get("/api/v1/quant-research/us/nvda?lang=zh")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and len(body["dimensions"]) == 5
    assert "source" not in json.dumps(body)
    assert seen == {"market": "us", "symbol": "nvda", "lang": "zh"}


def test_unsupported_market(client):
    c, _ = client
    body = c.get("/api/v1/quant-research/hk/0700").json()
    assert body["status"] == "unsupported_market" and body["status_note"]


def test_invalid_symbol_422(client):
    c, _ = client
    assert c.get("/api/v1/quant-research/us/%24%24%24").status_code == 422
    assert c.get("/api/v1/quant-research/us/NVDA?lang=fr").status_code == 422


def test_methodology_no_auth_needed():
    c = TestClient(app)
    for lang in ("zh", "en"):
        body = c.get(f"/api/v1/quant-research/methodology?lang={lang}").json()
        assert len(body["grade_bands"]) == 13 and len(body["dimensions"]) == 5
        assert sum(len(d["metrics"]) for d in body["dimensions"]) == 40
    from app.services.quant_research.copy import contains_forbidden
    text = json.dumps(body, ensure_ascii=False) + json.dumps(c.get("/api/v1/quant-research/methodology").json(),
                                                             ensure_ascii=False)
    assert contains_forbidden(text) == []
