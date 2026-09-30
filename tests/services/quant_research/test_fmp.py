"""FMP 拉取封装：429 重试与上报、非 200 返回 None。"""

import httpx

from app.cache import fmp_budget
from app.services.quant_research import fmp as fmp_mod
from app.services.quant_research.fmp import FmpClient


async def test_retries_after_429_and_reports(monkeypatch):
    calls = {"n": 0, "reported": []}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.params["symbol"] == "NVDA"
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=[{"date": "2026-09-29"}])

    async def fake_report(redis, priority, **_):
        calls["reported"].append(priority)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(fmp_mod.settings, "FMP_API_KEY", "k")
    monkeypatch.setattr(fmp_mod, "report_429", fake_report)
    monkeypatch.setattr(fmp_mod.asyncio, "sleep", no_sleep)
    fmp_budget.reset_local_state()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        data = await FmpClient(c, None, "batch").profile("NVDA")
    assert data == [{"date": "2026-09-29"}]
    assert calls["reported"] == ["batch"]


async def test_non_200_returns_none(monkeypatch):
    monkeypatch.setattr(fmp_mod.settings, "FMP_API_KEY", "k")
    fmp_budget.reset_local_state()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(402))) as c:
        assert await FmpClient(c, None, "user").profile("0700.HK") is None
