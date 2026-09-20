"""信号雷达 universe 完整性单测（覆盖科技窄基 + 大盘宽基）。"""
from __future__ import annotations

from app.services.signal_radar.universe import (
    all_universes,
    get_universe,
    list_universes,
    resolve_name,
    supported_markets,
)
from app.utils.market import Market, detect_market


class TestUniverse:
    def test_supported_markets(self):
        assert set(supported_markets()) == {"us", "cn", "hk"}

    def test_unknown_market_returns_none(self):
        assert get_universe("jp") is None

    def test_default_universe_per_market(self):
        # 每个市场默认 universe 就是原来的科技指数
        assert get_universe("us").key == "nasdaq100"
        assert get_universe("cn").key == "star50"
        assert get_universe("hk").key == "hstech"
        for m in supported_markets():
            assert get_universe(m).is_default

    def test_each_market_has_two_universes(self):
        # 每个市场：科技窄基 + 大盘宽基，默认排在前
        expected = {"us": ["nasdaq100", "sp500"], "cn": ["star50", "csi300"], "hk": ["hstech", "hsi"]}
        for m, keys in expected.items():
            got = [u.key for u in list_universes(m)]
            assert got == keys, f"{m} universe 列表不符：{got}"
            assert list_universes(m)[0].is_default

    def test_get_universe_by_key(self):
        u = get_universe("us", "sp500")
        assert u is not None and u.key == "sp500" and not u.is_default
        assert get_universe("us", "does_not_exist") is None
        # 跨市场键不串：cn 下没有 sp500
        assert get_universe("cn", "sp500") is None

    def test_each_universe_has_constituents_and_name(self):
        for u in all_universes():
            assert u.etf_name, f"{u.market}/{u.key} 缺展示名"
            assert len(u.constituents) >= 20, f"{u.market}/{u.key} 静态清单不足 20"

    def test_no_duplicate_symbols_within_universe(self):
        for u in all_universes():
            symbols = [s for s, _ in u.constituents]
            assert len(symbols) == len(set(symbols)), f"{u.market}/{u.key} 有重复代码"

    def test_all_names_present(self):
        for u in all_universes():
            for sym, name in u.constituents:
                assert name and name.strip(), f"{u.market}/{u.key}:{sym} 缺名称"

    def test_symbols_match_expected_market(self):
        expected = {"us": Market.US, "cn": Market.CN, "hk": Market.HK}
        for u in all_universes():
            for sym, _ in u.constituents:
                assert detect_market(sym) == expected[u.market], (
                    f"{u.market}/{u.key} 的 {sym} 市场判别不符"
                )


class TestResolveName:
    def test_resolves_curated_names_across_markets(self):
        assert resolve_name("us", "NVDA") == "英伟达"
        assert resolve_name("cn", "688981") == "中芯国际"
        assert resolve_name("hk", "2015") == "理想汽车"

    def test_symbol_case_insensitive(self):
        assert resolve_name("us", "nvda") == "英伟达"

    def test_hk_code_zero_padded(self):
        # 港股裸码零补齐到 4 位再查（"700" → "0700"）
        assert resolve_name("hk", "700") == "腾讯控股"
        assert resolve_name("hk", "0700") == "腾讯控股"

    def test_unknown_symbol_or_market_returns_none(self):
        assert resolve_name("us", "FIG") is None      # 不在任何 curated 成分里
        assert resolve_name("jp", "7203") is None      # 不支持的市场
