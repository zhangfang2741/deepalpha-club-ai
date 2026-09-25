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


class TestEastmoneyUsName:
    """东方财富美股搜索接口的中文名解析（纯函数）+ 批量解析的缓存行为（假 redis，不联网）。"""

    def test_matches_exact_code_and_common_stock(self):
        from app.services.signal_radar.constituents import parse_eastmoney_us_suggest

        # 真实响应形状：同代码前缀还挂着债券/优先股条目，必须精确匹配 Code 且 TypeUS=1
        payload = {"QuotationCodeTable": {"Data": [
            {"Code": "AAPL", "Name": "苹果", "Classify": "UsStock", "TypeUS": "1"},
            {"Code": "AAPL22", "Name": "Apple Inc Notes 2022", "Classify": "UsStock", "TypeUS": "6"},
        ]}}
        assert parse_eastmoney_us_suggest(payload, "AAPL") == "苹果"

    def test_skips_preferred_and_non_us_entries(self):
        from app.services.signal_radar.constituents import parse_eastmoney_us_suggest

        payload = {"QuotationCodeTable": {"Data": [
            {"Code": "ORCL_D", "Name": "Oracle Corp Series D Pfd", "Classify": "UsStock", "TypeUS": "2"},
        ]}}
        assert parse_eastmoney_us_suggest(payload, "ORCL_D") is None

    def test_no_match_returns_none(self):
        from app.services.signal_radar.constituents import parse_eastmoney_us_suggest

        payload = {"QuotationCodeTable": {"Data": [
            {"Code": "BRRR", "Name": "Coinshares Bitcoin ETF", "Classify": "UsStock", "TypeUS": "5"},
        ]}}
        assert parse_eastmoney_us_suggest(payload, "COIN") is None

    def test_malformed_payload_returns_none(self):
        from app.services.signal_radar.constituents import parse_eastmoney_us_suggest

        assert parse_eastmoney_us_suggest({"QuotationCodeTable": None}, "AAPL") is None
        assert parse_eastmoney_us_suggest("oops", "AAPL") is None

    def test_strips_trailing_ticker_suffix(self):
        """代码已单独显示在气泡第一行，名字里重复的英文代码括注要去掉。"""
        from app.services.signal_radar.constituents import parse_eastmoney_us_suggest

        payload = {"QuotationCodeTable": {"Data": [
            {"Code": "T", "Name": "美国电话电报(AT&T)", "Classify": "UsStock", "TypeUS": "1"},
        ]}}
        assert parse_eastmoney_us_suggest(payload, "T") == "美国电话电报"

    def test_strip_ticker_suffix_leaves_plain_name_untouched(self):
        from app.services.signal_radar.constituents import strip_ticker_suffix

        assert strip_ticker_suffix("苹果") == "苹果"
        assert strip_ticker_suffix("美国电话电报(AT&T)") == "美国电话电报"
        assert strip_ticker_suffix("美国电话电报（AT&T）") == "美国电话电报"


class _FakeRedis:
    """只实现所需命令的内存替身：set(ex=) / get。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


async def test_resolve_us_names_caches_and_skips_refetch(monkeypatch):
    """命中缓存的代码不再查东方财富；新查到的名称写回缓存供下次直接命中。"""
    from app.services.signal_radar import constituents as mod

    calls: list[str] = []

    async def fake_fetch(client, symbol):
        calls.append(symbol)
        return {"AAPL": "苹果", "ORCL": "甲骨文"}.get(symbol)

    monkeypatch.setattr(mod, "_fetch_eastmoney_us_name", fake_fetch)
    redis = _FakeRedis()
    await redis.set(f"{mod._US_NAME_CACHE_PREFIX}:MSFT", "微软")

    result = await mod._resolve_us_names(["AAPL", "ORCL", "MSFT", "ZZZZ"], redis=redis)

    assert result == {"AAPL": "苹果", "ORCL": "甲骨文", "MSFT": "微软"}
    assert sorted(calls) == ["AAPL", "ORCL", "ZZZZ"]  # MSFT 命中缓存，没有发起查询
    assert redis.store[f"{mod._US_NAME_CACHE_PREFIX}:AAPL"] == "苹果"  # 新查到的写回缓存


async def test_resolve_us_names_without_redis_still_works(monkeypatch):
    """无 redis（如未配置）时跳过缓存读写，仍能查询并返回结果。"""
    from app.services.signal_radar import constituents as mod

    async def fake_fetch(client, symbol):
        return "苹果" if symbol == "AAPL" else None

    monkeypatch.setattr(mod, "_fetch_eastmoney_us_name", fake_fetch)
    result = await mod._resolve_us_names(["AAPL", "ZZZZ"], redis=None)
    assert result == {"AAPL": "苹果"}


async def test_resolve_constituents_enriches_us_names_beyond_curated(monkeypatch):
    """resolve_constituents 端到端：curated 清单之外的美股代码也能拿到中文名（东方财富补充）。"""
    from app.services.signal_radar import constituents as mod

    # ORCL 不在 nasdaq100 的 curated 清单里，验证它会走东方财富补齐；动态结果要
    # >= _MIN_VALID 只才不会被判定「结果太少」回退回纯静态清单（纯字母代码才是合法美股代码）
    async def fake_dynamic(universe):
        filler = [(f"{chr(65 + i // 26)}{chr(65 + i % 26)}X", "filler", 0.0) for i in range(25)]
        return [("AAPL", "Apple", 10.0), ("ORCL", "Oracle", 5.0), *filler]

    async def fake_eastmoney(client, symbol):
        return {"ORCL": "甲骨文"}.get(symbol)

    monkeypatch.setattr(mod, "_fetch_dynamic", fake_dynamic)
    monkeypatch.setattr(mod, "_fetch_eastmoney_us_name", fake_eastmoney)
    redis = _FakeRedis()

    resolved = await mod.resolve_constituents("us", redis=redis, universe_key="nasdaq100")

    assert dict(resolved)["AAPL"] == "苹果"   # curated 清单命中
    assert dict(resolved)["ORCL"] == "甲骨文"  # 东方财富补齐，之前会是空字符串


def _fake_dynamic_with_orcl():
    async def fake_dynamic(universe):
        filler = [(f"{chr(65 + i // 26)}{chr(65 + i % 26)}X", "filler", 0.0) for i in range(25)]
        return [("AAPL", "Apple", 10.0), ("ORCL", "Oracle", 5.0), *filler]
    return fake_dynamic


async def test_resolve_constituents_reads_cache_by_default(monkeypatch):
    """不刷新时命中成分股缓存就直接返回，不重新拉取来源。"""
    import json

    from app.services.signal_radar import constituents as mod

    async def boom(universe):
        raise AssertionError("命中缓存时不应再拉取来源")

    monkeypatch.setattr(mod, "_fetch_dynamic", boom)
    redis = _FakeRedis()
    await redis.set(f"{mod._CACHE_PREFIX}:us:nasdaq100", json.dumps([["ORCL", ""]]))

    resolved = await mod.resolve_constituents("us", redis=redis, universe_key="nasdaq100")
    assert resolved == [("ORCL", "")]


async def test_resolve_constituents_refresh_rebuilds_stale_names(monkeypatch):
    """refresh=True 跳过成分股缓存重新解析：旧缓存里没解析出中文名的标的这次能补上。"""
    import json

    from app.services.signal_radar import constituents as mod

    async def fake_eastmoney(client, symbol):
        return {"ORCL": "甲骨文"}.get(symbol)

    monkeypatch.setattr(mod, "_fetch_dynamic", _fake_dynamic_with_orcl())
    monkeypatch.setattr(mod, "_fetch_eastmoney_us_name", fake_eastmoney)
    redis = _FakeRedis()
    cache_key = f"{mod._CACHE_PREFIX}:us:nasdaq100"
    await redis.set(cache_key, json.dumps([["ORCL", ""]]))

    resolved = await mod.resolve_constituents("us", redis=redis, universe_key="nasdaq100", refresh=True)

    assert dict(resolved)["ORCL"] == "甲骨文"
    assert dict(json.loads(redis.store[cache_key]))["ORCL"] == "甲骨文"  # 新结果写回缓存
