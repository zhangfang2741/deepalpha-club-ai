"""信号雷达成分股映射纯逻辑单测（不触发任何网络）。"""
from __future__ import annotations

from app.services.signal_radar.constituents import _map_to_universe


class TestMapToUniverse:
    def test_zero_weight_keeps_source_order(self):
        # sp500/akshare 端点不带权重（全 0）时，应保持来源原始顺序，不乱序
        raw = [("AAPL", "Apple", 0.0), ("MSFT", "Microsoft", 0.0), ("NVDA", "Nvidia", 0.0)]
        out = _map_to_universe(raw, {"AAPL": "苹果"}, max_scan=10)
        assert [s for s, _ in out] == ["AAPL", "MSFT", "NVDA"]
        # 有中文名优先用中文名，缺失回退来源名
        assert dict(out)["AAPL"] == "苹果"
        assert dict(out)["MSFT"] == "Microsoft"

    def test_weighted_sorted_desc(self):
        raw = [("A", "a", 1.0), ("B", "b", 9.0), ("C", "c", 5.0)]
        out = _map_to_universe(raw, {}, max_scan=10)
        assert [s for s, _ in out] == ["B", "C", "A"]

    def test_max_scan_caps(self):
        # 50 个合法的纯字母美股代码，max_scan=10 应只留前 10
        raw = [(f"{chr(65 + i // 26)}{chr(65 + i % 26)}X", "n", 0.0) for i in range(50)]
        out = _map_to_universe(raw, {}, max_scan=10)
        assert len(out) == 10

    def test_dedup_and_drop_invalid(self):
        # 重复代码只留一个；无法判别市场的代码丢弃
        raw = [("AAPL", "a", 0.0), ("AAPL", "a2", 0.0), ("!!!", "bad", 0.0), ("MSFT", "m", 0.0)]
        out = _map_to_universe(raw, {}, max_scan=10)
        assert [s for s, _ in out] == ["AAPL", "MSFT"]

    def test_hk_symbol_normalized(self):
        # 港股会被 normalize 补零到 5 位（0700 → 00700）
        raw = [("0700.HK", "Tencent", 0.0)]
        out = _map_to_universe(raw, {"00700": "腾讯控股"}, max_scan=10)
        assert out == [("00700", "腾讯控股")]


class TestDynamicSources:
    """新成分来源的解析（纯函数，不联网）。

    FMP 套餐不含成分端点（402），改用纳斯达克官方列表（纳指100）、维基百科成分表（标普500）、
    akshare 中证指数（科创50）。
    """

    def test_parse_nasdaq100_api(self):
        from app.services.signal_radar.constituents import parse_nasdaq100

        payload = {"data": {"data": {"rows": [
            {"symbol": "AAPL", "companyName": "Apple Inc. Common Stock"},
            {"symbol": "GOOGL", "companyName": "Alphabet Inc. Class A Common Stock"},
            {"symbol": "", "companyName": "bad"},
        ]}}}
        assert parse_nasdaq100(payload) == [("AAPL", "Apple", 0.0), ("GOOGL", "Alphabet", 0.0)]

    def test_parse_nasdaq100_bad_payload(self):
        from app.services.signal_radar.constituents import parse_nasdaq100

        assert parse_nasdaq100({"data": None}) == []
        assert parse_nasdaq100("oops") == []

    def test_parse_wiki_sp500(self):
        from app.services.signal_radar.constituents import parse_wiki_sp500

        html = """<table class="wikitable"><thead><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr></thead>
        <tbody>""" + "".join(f"<tr><td>S{i:03d}</td><td>Co {i}</td><td>IT</td></tr>" for i in range(120)) + \
            "<tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Fin</td></tr></tbody></table>"
        rows = parse_wiki_sp500(html)
        assert len(rows) == 121
        assert rows[0] == ("S000", "Co 0", 0.0)
        assert rows[-1] == ("BRK-B", "Berkshire Hathaway", 0.0)  # 转成行情源的代码形态

    def test_clean_us_name(self):
        from app.services.signal_radar.constituents import clean_us_name

        assert clean_us_name("Apple Inc. Common Stock") == "Apple"
        assert clean_us_name("Alphabet Inc. Class C Capital Stock") == "Alphabet"
        assert clean_us_name("Meta Platforms, Inc. Class A Common Stock") == "Meta Platforms"
        assert clean_us_name("NVIDIA Corporation Common Stock") == "NVIDIA"
        assert clean_us_name("American Electric Power Company, Inc. Common Stock") == "American Electric Power"


def test_tech_universes_scan_full_index():
    """科技池扫描上限覆盖完整指数（纳指100 约 101 只），科创50 走 akshare 中证指数。"""
    from app.services.signal_radar.universe import SOURCE_AKSHARE_INDEX, get_universe

    assert get_universe("us", "nasdaq100").max_scan >= 101
    star = get_universe("cn", "star50")
    assert star.source == SOURCE_AKSHARE_INDEX and star.source_arg == "000688"
    assert len(get_universe("hk", "hstech").constituents) >= 30


def test_us_symbols_without_chinese_name_get_empty_name():
    """美股没拿到中文名时名称留空（气泡只显示代码），不回退到太长的英文全称。"""
    raw = [("AAPL", "Apple", 0.0), ("AEP", "American Electric Power", 0.0)]
    out = _map_to_universe(raw, {"AAPL": "苹果"}, max_scan=10, fallback_to_source_name=False)
    assert out == [("AAPL", "苹果"), ("AEP", "")]
