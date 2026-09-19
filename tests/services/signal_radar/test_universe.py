"""信号雷达 universe 完整性单测。"""
from __future__ import annotations

from app.services.signal_radar.universe import (
    get_universe,
    supported_markets,
)
from app.utils.market import Market, detect_market


class TestUniverse:
    def test_supported_markets(self):
        assert set(supported_markets()) == {"us", "cn", "hk"}

    def test_unknown_market_returns_none(self):
        assert get_universe("jp") is None

    def test_each_market_has_constituents_and_etf(self):
        for m in supported_markets():
            u = get_universe(m)
            assert u is not None
            assert u.etf_name
            assert len(u.constituents) >= 20

    def test_no_duplicate_symbols(self):
        for m in supported_markets():
            u = get_universe(m)
            symbols = [s for s, _ in u.constituents]
            assert len(symbols) == len(set(symbols)), f"{m} 有重复代码"

    def test_all_names_present(self):
        for m in supported_markets():
            u = get_universe(m)
            for sym, name in u.constituents:
                assert name and name.strip(), f"{m}:{sym} 缺名称"

    def test_symbols_match_expected_market(self):
        expected = {"us": Market.US, "cn": Market.CN, "hk": Market.HK}
        for m in supported_markets():
            u = get_universe(m)
            for sym, _ in u.constituents:
                assert detect_market(sym) == expected[m], f"{m} 的 {sym} 市场判别不符"
