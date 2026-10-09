"""按名称 / 代码搜股票（A 股、港股、美股中文名），供缠论分析页搜索框联想。"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import chan as chan_api
from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.services import symbol_lookup as sl

CN = {"603019": "中科曙光", "600519": "贵州茅台", "000858": "五粮液", "601088": "中国神华",
      "600036": "招商银行", "603000": "人民网"}


def test_rank_exact_code_first_then_prefix_then_name():
    table = {"603019": "中科曙光", "603000": "人民网", "600603": "ST兴业"}
    out = sl.rank_matches(table, "603019", 10)
    assert out[0] == ("603019", "中科曙光")
    prefix = [c for c, _ in sl.rank_matches(table, "603", 10)]
    assert prefix[:2] == ["603000", "603019"]  # 代码前缀先于代码包含（600603），同级按代码排


def test_rank_name_prefix_before_name_contains():
    table = {"1": "中国平安", "2": "平安银行", "3": "中国太平"}
    names = [n for _, n in sl.rank_matches(table, "平安", 10)]
    assert names == ["平安银行", "中国平安"]  # 名称前缀 > 名称包含


def test_rank_case_insensitive_and_strips_space_and_hk_zero_pad():
    table = {"0700": "腾讯控股", "9988": "阿里巴巴-W", "03690": "美团-W"}
    assert sl.rank_matches(table, " 腾讯 ", 5) == [("0700", "腾讯控股")]
    assert sl.rank_matches({"AAPL": "苹果"}, "aapl", 5) == [("AAPL", "苹果")]


def test_rank_empty_query_and_limit():
    assert sl.rank_matches(CN, "   ", 5) == []
    assert len(sl.rank_matches(CN, "中", 2)) == 2


@pytest.mark.asyncio
async def test_search_cn_uses_name_table():
    with patch.object(sl, "load_name_table", AsyncMock(return_value=CN)):
        out = await sl.search("cn", "曙光", redis=None, limit=5)
    assert out == [{"market": "cn", "symbol": "603019", "name": "中科曙光"}]


@pytest.mark.asyncio
async def test_search_falls_back_to_curated_when_fetch_fails():
    """全市场名单取不到（数据源挂了）时不能报错，退回雷达里写死的那几十只。"""
    with patch.object(sl, "_fetch_name_table", AsyncMock(side_effect=RuntimeError("boom"))):
        out = await sl.search("cn", "茅台", redis=None, limit=5)
    assert {"market": "cn", "symbol": "600519", "name": "贵州茅台"} in out


@pytest.mark.asyncio
async def test_search_us_chinese_name_uses_curated_not_fmp():
    with patch.object(sl, "search_us_symbols", AsyncMock(side_effect=AssertionError("不该调 FMP"))):
        out = await sl.search("us", "苹果", redis=None, limit=5)
    assert {"market": "us", "symbol": "AAPL", "name": "苹果"} in out


@pytest.mark.asyncio
async def test_search_us_ascii_goes_to_fmp_and_merges_curated():
    fmp = AsyncMock(return_value=[{"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"}])
    with patch.object(sl, "search_us_symbols", fmp):
        out = await sl.search("us", "AAPL", redis=None, limit=5)
    assert out[0]["symbol"] == "AAPL" and out[0]["name"] == "苹果"  # 有中文名的用中文名
    fmp.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_us_fmp_failure_still_returns_curated():
    with patch.object(sl, "search_us_symbols", AsyncMock(side_effect=RuntimeError("fmp down"))):
        out = await sl.search("us", "NVDA", redis=None, limit=5)
    assert out and out[0]["symbol"] == "NVDA"


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(chan_api.router, prefix="/chan")
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": 1})()
    app.dependency_overrides[get_redis] = lambda: None
    yield TestClient(app)


def test_endpoint_returns_matches(client):
    with patch.object(sl, "load_name_table", AsyncMock(return_value=CN)):
        r = client.get("/chan/symbol-search", params={"q": "曙光", "market": "cn"})
    assert r.status_code == 200
    assert r.json() == [{"market": "cn", "symbol": "603019", "name": "中科曙光"}]


def test_endpoint_rejects_bad_market_and_empty_q(client):
    assert client.get("/chan/symbol-search", params={"q": "x", "market": "jp"}).status_code == 422
    assert client.get("/chan/symbol-search", params={"q": "", "market": "cn"}).status_code == 422
