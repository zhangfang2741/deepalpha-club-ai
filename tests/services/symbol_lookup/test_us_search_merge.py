"""美股联想：FMP 的 search-symbol（按代码）与 search-name（按公司名）合并去重。"""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.skills import symbol_search as ss


def _row(sym, name="", ex="NASDAQ"):
    return {"symbol": sym, "name": name, "exchange": ex}


@pytest.mark.asyncio
async def test_fetch_merges_symbol_and_name_endpoints_dedup_symbol_first():
    async def fake(url, query, limit):
        if url == ss._FMP_SEARCH_URL:
            return [_row("APP", "AppLovin"), _row("AAPL", "Apple Inc.")]
        return [_row("AAPL", "Apple Inc."), _row("APLE", "Apple Hospitality REIT", "NYSE")]

    with patch.object(ss, "_fetch_endpoint", side_effect=fake):
        out = await ss._fetch_fmp_search("apple", 30)
    assert [r["symbol"] for r in out] == ["APP", "AAPL", "APLE"]


@pytest.mark.asyncio
async def test_one_endpoint_failing_still_returns_the_other():
    async def fake(url, query, limit):
        if url == ss._FMP_SEARCH_URL:
            raise RuntimeError("boom")
        return [_row("NVDA", "NVIDIA Corporation")]

    with patch.object(ss, "_fetch_endpoint", side_effect=fake):
        assert [r["symbol"] for r in await ss._fetch_fmp_search("nvidia", 30)] == ["NVDA"]


@pytest.mark.asyncio
async def test_both_failing_raises():
    with patch.object(ss, "_fetch_endpoint", AsyncMock(side_effect=RuntimeError("down"))):
        with pytest.raises(RuntimeError):
            await ss._fetch_fmp_search("x", 30)


@pytest.mark.asyncio
async def test_search_us_symbols_filters_exchanges_and_limits():
    rows = [_row("A", "a"), _row("B", "b", "OTC"), _row("C", "c", "NYSE")]
    with patch.object(ss, "_fetch_fmp_search", AsyncMock(return_value=rows)):
        out = await ss.search_us_symbols("q", redis=None, limit=1)
    assert out == [{"symbol": "A", "name": "a", "exchange": "NASDAQ"}]
