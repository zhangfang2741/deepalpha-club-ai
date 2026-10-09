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


# ───────── 冷缓存：不能让用户干等（A 股全市场名单冷拉要十几秒，iOS 请求超时后列表就是空的）─────────

@pytest.fixture(autouse=True)
def clean_caches():
    """进程内缓存 / 单飞任务 / 失败冷却都是模块级状态，每条测试前后清掉，免得互相串。"""
    def reset():
        for task in list(sl._INFLIGHT.values()):
            task.cancel()
        sl._MEM.clear()
        sl._INFLIGHT.clear()
        sl._FAILED_AT.clear()
    reset()
    yield
    reset()


@pytest.mark.asyncio
async def test_cold_cache_answers_immediately_with_curated_then_full_table(clean_caches):
    import asyncio

    gate = asyncio.Event()
    calls = 0

    async def slow_fetch(market):
        nonlocal calls
        calls += 1
        await gate.wait()
        return {**CN, **{f"9{i:05d}": f"股票{i}" for i in range(3000)}}  # 够 3000 只，不被当成残缺

    with patch.object(sl, "_fetch_name_table", slow_fetch):
        # 名单还没拉回来：几十毫秒内就要有结果，用写死的成分兜底（贵州茅台在里面）
        out = await asyncio.wait_for(sl.search("cn", "茅台", redis=None, limit=5, wait=0.05), timeout=2)
        assert {"market": "cn", "symbol": "600519", "name": "贵州茅台"} in out
        # 中科曙光不在写死的成分里，此时搜不到，是预期的降级
        assert await sl.search("cn", "曙光", redis=None, limit=5, wait=0.05) == []
        gate.set()
        await asyncio.wait_for(sl._INFLIGHT["cn"], timeout=2)  # 后台拉完
        # 拉完后全量可用
        out2 = await sl.search("cn", "曙光", redis=None, limit=5)
        assert out2 == [{"market": "cn", "symbol": "603019", "name": "中科曙光"}]
    assert calls == 1  # 前面两次搜索共用同一次后台拉取（单飞），不会每次输入都去打东财


@pytest.mark.asyncio
async def test_concurrent_cold_searches_fetch_only_once(clean_caches):
    import asyncio

    calls = 0

    async def fetch(market):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {f"6{i:05d}": f"名{i}" for i in range(3500)}

    with patch.object(sl, "_fetch_name_table", fetch):
        await asyncio.gather(*[sl.search("cn", "名", redis=None, limit=3, wait=1) for _ in range(8)])
        await asyncio.wait_for(sl._INFLIGHT["cn"], timeout=2) if "cn" in sl._INFLIGHT else None
    assert calls == 1


@pytest.mark.asyncio
async def test_failed_background_fetch_is_retried_next_time(clean_caches):
    import asyncio

    seq = [RuntimeError("down"), {f"6{i:05d}": f"名{i}" for i in range(3500)}]

    async def fetch(market):
        v = seq.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    with patch.object(sl, "_fetch_name_table", fetch), patch.object(sl, "_FAIL_COOLDOWN", 0.0):
        await sl.search("cn", "名1", redis=None, limit=3, wait=1)  # 第一次失败，退回写死成分，不抛
        await asyncio.sleep(0.01)
        out = await sl.search("cn", "名1", redis=None, limit=3, wait=1)  # 第二次重新拉
    assert out and out[0]["symbol"].startswith("6")


@pytest.mark.asyncio
async def test_failure_cooldown_does_not_hammer_source(clean_caches):
    calls = 0

    async def fetch(market):
        nonlocal calls
        calls += 1
        raise RuntimeError("down")

    with patch.object(sl, "_fetch_name_table", fetch):
        for _ in range(5):
            out = await sl.search("cn", "茅台", redis=None, limit=3, wait=1)
            assert out and out[0]["symbol"] == "600519"  # 一直能用兜底答复
    assert calls == 1  # 冷却期内不重复去打数据源
