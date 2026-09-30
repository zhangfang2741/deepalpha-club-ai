"""请求入口：不支持市场、读批量结果与缓存、无批量时数据不足。"""

import json

from app.services.quant_research import service
from tests.services.quant_research.fixtures import FIXTURE_DIR


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


async def test_unsupported_market():
    out = await service.get_quant_research("hk", "0700", "zh", redis=None)
    assert out.status == "unsupported_market" and out.status_note == "量化研究暂只支持美股"


async def test_reads_db_result_and_caches(monkeypatch):
    payload = json.loads((FIXTURE_DIR / "golden_NVDA.json").read_text())

    class Row:
        payload_zh = payload
        payload_en = payload

    calls = {"db": 0}

    async def latest(market, symbol):
        calls["db"] += 1
        return Row()

    monkeypatch.setattr(service.repo, "get_latest_result", latest)
    r = _FakeRedis()
    out = await service.get_quant_research("US", "nvda", "zh", redis=r)
    assert out.symbol == "NVDA" and calls["db"] == 1
    assert "quant:us:sym:NVDA:zh" in r.store
    await service.get_quant_research("us", "NVDA", "zh", redis=r)
    assert calls["db"] == 1  # 第二次命中缓存


async def test_no_batch_yet_is_insufficient(monkeypatch):
    async def none(*a, **k):
        return None

    monkeypatch.setattr(service.repo, "get_latest_result", none)
    monkeypatch.setattr(service.repo, "latest_distribution_date", none)
    out = await service.get_quant_research("us", "RKLB", "en", redis=None)
    assert out.status == "insufficient_data"
    assert "not ready" in (out.status_note or "")


async def test_class_share_symbol_normalized(monkeypatch):
    seen = {}

    async def latest(market, symbol):
        seen["symbol"] = symbol
        return None

    async def none(*a, **k):
        return None

    monkeypatch.setattr(service.repo, "get_latest_result", latest)
    monkeypatch.setattr(service.repo, "latest_distribution_date", none)
    await service.get_quant_research("us", "brk.b", "zh", redis=None)
    assert seen["symbol"] == "BRK-B"
