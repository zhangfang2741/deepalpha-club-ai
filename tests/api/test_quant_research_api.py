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
    assert body["status"] == "ok" and len(body["dimensions"]) == 6
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
        assert len(body["grade_bands"]) == 13 and len(body["dimensions"]) == 6
        assert sum(len(d["metrics"]) for d in body["dimensions"]) == 45
    from app.services.quant_research.copy import contains_forbidden
    text = json.dumps(body, ensure_ascii=False) + json.dumps(c.get("/api/v1/quant-research/methodology").json(),
                                                             ensure_ascii=False)
    assert contains_forbidden(text) == []


def test_batch_run_endpoint_lock_semantics(client, monkeypatch):
    """手动触发批量：锁被占返回 already_running，空闲返回 started。"""
    from datetime import UTC, datetime

    from app.services.quant_research.scheduler import _lock_key, last_us_session

    class FakeRedis:
        def __init__(self):
            self.keys: set[str] = set()

        async def set(self, key, value, ex=None, nx=False):
            if nx:
                if key in self.keys:
                    return False
                self.keys.add(key)
                return True
            return True

        async def delete(self, key):
            self.keys.discard(key)

    async def noop(day, *, redis, client=None):
        return {"ok": True}

    fake = FakeRedis()
    monkeypatch.setattr(api_mod, "run_us_batch", noop)
    monkeypatch.setattr(api_mod, "current_redis", lambda: fake)
    day = last_us_session(datetime.now(UTC))
    fake.keys.add(_lock_key("us", day))  # 模拟定时批量正在跑
    assert client[0].post("/api/v1/quant-research/batch/run").json() == {
        "status": "already_running", "market": "us", "day": day.isoformat()}
    fake.keys.clear()
    body = client[0].post("/api/v1/quant-research/batch/run").json()
    assert body["status"] == "started" and body["day"] == day.isoformat()


async def test_run_manual_batch_releases_lock_on_failure(monkeypatch):
    """后台批量失败也释放锁，不挡当晚定时批。"""
    from datetime import date

    from app.api.v1 import quant_research as api
    from app.services.quant_research.scheduler import _lock_key

    async def boom(day, *, redis, client=None):
        raise RuntimeError("跑批炸了")

    class FakeRedis:
        def __init__(self):
            self.deleted: list[str] = []

        async def delete(self, key):
            self.deleted.append(key)

    fake = FakeRedis()
    monkeypatch.setattr(api, "run_us_batch", boom)
    monkeypatch.setattr(api, "current_redis", lambda: fake)
    await api._run_manual_batch("us", date(2026, 9, 29))
    assert fake.deleted == [_lock_key("us", date(2026, 9, 29))]

    monkeypatch.setattr(api, "run_hk_batch", boom)
    await api._run_manual_batch("hk", date(2026, 10, 2))
    assert fake.deleted[-1] == _lock_key("hk", date(2026, 10, 2))
