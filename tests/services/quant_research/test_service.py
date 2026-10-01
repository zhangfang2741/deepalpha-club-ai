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
    assert out.status == "unsupported_market" and out.status_note == "基本面研究暂只支持美股"


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
    assert service._cache_key("NVDA", "zh") in r.store
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


async def test_legacy_cache_receives_guidance_without_recomputation(monkeypatch):
    payload = json.loads((FIXTURE_DIR / "golden_NVDA.json").read_text())
    for dimension in payload["dimensions"]:
        for group in dimension["groups"]:
            for metric in group["metrics"]:
                metric.pop("interpretation", None)

    async def unexpected(*args, **kwargs):
        raise AssertionError("缓存命中时不应查询数据库或重新计算")

    monkeypatch.setattr(service.repo, "get_latest_result", unexpected)
    redis = _FakeRedis()
    redis.store[service._cache_key("NVDA", "zh")] = json.dumps(payload)
    out = await service.get_quant_research("us", "NVDA", "zh", redis=redis)
    metrics = [metric for dimension in out.dimensions for group in dimension.groups for metric in group.metrics]
    assert all(metric.interpretation and metric.interpretation.role for metric in metrics)
    assert out.overall.model_dump() == payload["overall"]


async def test_cache_from_older_methodology_is_ignored(monkeypatch):
    """改规则部署后，旧版本缓存的结果（如样本外现算的旧阶段）不再命中。"""
    calls = {"db": 0}

    class Row:
        payload_zh = json.loads((FIXTURE_DIR / "golden_NVDA.json").read_text())
        payload_en = payload_zh

    async def latest(*args, **kwargs):
        calls["db"] += 1
        return Row()

    monkeypatch.setattr(service.repo, "get_latest_result", latest)
    redis = _FakeRedis()
    redis.store["quant:us:sym:NVDA:zh"] = json.dumps({"stale": True})  # 旧格式键
    await service.get_quant_research("us", "NVDA", "zh", redis=redis)
    assert calls["db"] == 1
    assert service.METHODOLOGY_VERSION in service._cache_key("NVDA", "zh")


async def test_moat_attached_at_read_time_and_not_cached(monkeypatch):
    """护城河读取时附上：有评估 → 宽 / 窄 / 无；样本内没评估 → 评估中；不写进评分缓存。"""
    from datetime import datetime

    payload = json.loads((FIXTURE_DIR / "golden_NVDA.json").read_text())

    class Row:
        payload_zh = payload
        payload_en = payload

    class Moat:
        rating, trend, filed_date, tenk_url = "wide", "widening", "2026-02-25", "https://sec.gov/x"
        evidence = {"metric": "roic", "years": [[2025, 0.6], [2024, 0.5]], "cost_of_capital": 0.1,
                    "years_above": 2, "n_years": 2, "avg_spread": 0.45, "level": "strong"}
        sources = [{"source": "switching_costs", "strength": "strong", "reason_zh": "开发者被 CUDA 绑定",
                    "reason_en": "Developers are tied to CUDA", "quotes": ["CUDA ..."]}]
        threats = {"zh": "客户自研芯片", "en": "Customers building their own chips"}
        assessed_at = datetime(2026, 10, 1)

    async def latest(market, symbol):
        return Row()

    moat_rows = {"value": Moat()}

    async def latest_moat(market, symbol, version):
        return moat_rows["value"]

    monkeypatch.setattr(service.repo, "get_latest_result", latest)
    monkeypatch.setattr(service.repo, "latest_moat", latest_moat)
    r = _FakeRedis()
    out = await service.get_quant_research("us", "NVDA", "zh", redis=r)
    assert out.moat and out.moat.status == "ok" and out.moat.rating_name == "宽护城河"
    assert out.moat.trend_name == "超额回报在扩大" and out.moat.summary == "主要来源：转换成本"
    assert "过去 2 年里 2 年 ROIC 高于资金成本" in out.moat.evidence.text
    cached = json.loads(r.store[service._cache_key("NVDA", "zh")])
    assert cached.get("moat") is None  # 评分缓存里不带护城河，评完即可见

    moat_rows["value"] = None
    out2 = await service.get_quant_research("us", "NVDA", "en", redis=r)
    assert out2.moat.status == "pending" and out2.moat.rating is None
