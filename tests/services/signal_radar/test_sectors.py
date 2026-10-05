"""雷达按行业：标签、计数、行业池与计数一致、池子读写。"""
import json

from app.schemas.signal_radar import RadarDayOut, RadarSignalOut
from app.services.signal_radar import sectors
from app.services.signal_radar.service import _sector_pools


def _sig(symbol: str, side: str = "buy", signal_type: str = "buy1", strength: float = 0.5) -> RadarSignalOut:
    return RadarSignalOut(symbol=symbol, name=symbol, side=side, label="一买", signal_type=signal_type,
                          date="2026-09-30", price=1.0, strength=strength, bias="neutral",
                          signal_strength="medium", confirmed=True, pivot_stage_depth=0.5, age_days=0)


def test_us_tags_follow_gics_sector():
    tags = sectors.us_tags_from_sp1500({
        "NVDA": ("NVIDIA", "information_technology"), "MSFT": ("Microsoft", "information_technology"),
        "XOM": ("Exxon", "energy"), "ZZZ": ("Unknown", "unknown"),
    })
    assert tags == {"NVDA": "technology", "MSFT": "technology", "XOM": "energy"}


def test_sector_keys_match_regime_sectors():
    from app.services.regime.constants import SECTORS

    regime_keys = {s["key"] for s in SECTORS}
    assert set(sectors.GICS_TO_SECTOR.values()) == regime_keys


def test_tag_and_count_skip_untagged():
    sigs = sectors.tag_signals([_sig("NVDA"), _sig("AMD", "sell", "sell1"), _sig("XOM"), _sig("ASML")],
                               {"NVDA": "technology", "AMD": "technology", "XOM": "energy"})
    assert sigs[3].sector is None
    assert sectors.sector_counts(sigs) == {"technology": {"buy": 1, "sell": 1}, "energy": {"buy": 1, "sell": 0}}


def test_dotted_symbol_normalized():
    [s] = sectors.tag_signals([_sig("BRK.B")], {"BRK-B": "financials"})
    assert s.sector == "financials"


def test_pools_consistent_with_counts_and_capped():
    tags = {f"S{i}": "technology" for i in range(15)} | {"E1": "energy"}
    day = RadarDayOut(date="2026-09-30", buy_count=0, sell_count=0,
                      signals=[_sig(f"S{i}", strength=i / 15) for i in range(15)] + [_sig("E1", "sell", "sell1")])
    pools = _sector_pools(day, tags, top_n=10)
    assert day.sector_counts == {"technology": {"buy": 15, "sell": 0}, "energy": {"buy": 0, "sell": 1}}
    assert len(pools["technology"]) == 10
    assert all(s.sector == "technology" for s in pools["technology"])
    assert [s.symbol for s in pools["energy"]] == ["E1"]
    assert _sector_pools(day, {}, top_n=10) == {}


def test_merge_sub_levels():
    pooled = _sig("NVDA")
    ranked = _sig("NVDA")
    ranked.sub_level_verdict, ranked.sub_level_label = "resonance_buy", "共振买点"
    sectors.merge_sub_levels({"technology": [pooled]}, [ranked])
    assert pooled.sub_level_verdict == "resonance_buy"


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)


async def test_pool_roundtrip():
    redis = _FakeRedis()
    s = _sig("NVDA")
    s.sector = "technology"
    await sectors.write_pools(redis, "ns", "us", "sp500", {"2026-09-30": {"technology": [s]}}, ttl=60)
    got = await sectors.read_pool(redis, "ns", "us", "sp500", "2026-09-30", "technology")
    assert got is not None and [x.symbol for x in got] == ["NVDA"]
    assert await sectors.read_pool(redis, "ns", "us", "sp500", "2026-09-30", "energy") == []
    assert await sectors.read_pool(redis, "ns", "us", "sp500", "2026-09-29", "energy") is None
    assert json.loads(redis.store["signal_radar:sector:ns:us:sp500:2026-09-30"])["technology"][0]["sector"]


async def test_read_pools_returns_every_sector_of_the_day():
    """一次取回当天全部行业池（App 切行业不用再请求）；没有池为 None。"""
    redis = _FakeRedis()
    a, b = _sig("NVDA"), _sig("XOM", side="sell", signal_type="sell2")
    await sectors.write_pools(redis, "ns", "us", "nasdaq100", {"2026-09-30": {"technology": [a], "energy": [b]}},
                              ttl=60)
    got = await sectors.read_pools(redis, "ns", "us", "nasdaq100", "2026-09-30")
    assert got is not None and {k: [s.symbol for s in v] for k, v in got.items()} == {
        "technology": ["NVDA"], "energy": ["XOM"]}
    assert await sectors.read_pools(redis, "ns", "us", "nasdaq100", "2026-09-29") is None
    redis.store["signal_radar:sector:ns:us:nasdaq100:2026-09-28"] = "{bad"
    assert await sectors.read_pools(redis, "ns", "us", "nasdaq100", "2026-09-28") is None


async def test_sector_pools_response_counts(monkeypatch):
    from app.services.signal_radar import service as svc

    redis = _FakeRedis()
    await sectors.write_pools(redis, svc._mode_ns("loose"), "us", "nasdaq100", {"2026-09-30": {
        "technology": [_sig("NVDA"), _sig("AMD", side="sell", signal_type="sell1")]}}, ttl=60)
    out = await svc.sector_pools(redis, "us", "nasdaq100", "2026-09-30", "loose")
    assert out.available and out.universe == "nasdaq100" and out.date == "2026-09-30"
    assert [s.symbol for s in out.sectors["technology"]] == ["NVDA", "AMD"]
    missing = await svc.sector_pools(redis, "us", "nasdaq100", "2026-09-29", "loose")
    assert not missing.available and missing.sectors == {}


def test_cn_tags_use_shenwan_level1_not_gics():
    from types import SimpleNamespace as NS

    tags = sectors.cn_tags_from_meta({
        "600519": NS(industry="白酒Ⅱ"), "300750": NS(industry="电池"), "688981": NS(industry="半导体"),
        "000001": NS(industry="银行Ⅱ"), "999999": NS(industry="没见过的行业"),
    })
    assert tags == {"600519": "食品饮料", "300750": "电力设备", "688981": "电子", "000001": "银行"}


def test_cn_sw_map_covers_all_known_industries_with_31_level1():
    from app.services.quant_research.cnhk.sectors import CN_INDUSTRY_TO_GICS, CN_INDUSTRY_TO_SW, SW_LEVEL1

    assert set(CN_INDUSTRY_TO_SW) == set(CN_INDUSTRY_TO_GICS)
    assert len(SW_LEVEL1) == 31 and set(CN_INDUSTRY_TO_SW.values()) == set(SW_LEVEL1)


def test_hk_tags_use_hang_seng_level1_not_gics():
    from types import SimpleNamespace as NS

    tags = sectors.hk_tags_from_meta({
        "00700": NS(industry="软件服务"), "00939": NS(industry="银行"), "01211": NS(industry="汽车"),
        "09999": NS(industry="没见过的行业"),
    })
    assert tags == {"00700": "资讯科技业", "00939": "金融业", "01211": "非必需性消费"}


def test_hk_hs_map_covers_all_known_industries_with_12_level1():
    from app.services.quant_research.cnhk.sectors import HK_INDUSTRY_TO_GICS, HK_INDUSTRY_TO_HS, HS_LEVEL1

    assert set(HK_INDUSTRY_TO_HS) == set(HK_INDUSTRY_TO_GICS)
    assert len(HS_LEVEL1) == 12 and set(HK_INDUSTRY_TO_HS.values()) == set(HS_LEVEL1)


def test_lookup_tag_pads_hk_and_strips_suffix():
    tags = {"00700": "communication", "600519": "staples", "BRK-B": "financials"}
    assert sectors.lookup_tag(tags, "0700") == "communication"
    assert sectors.lookup_tag(tags, "700.HK") == "communication"
    assert sectors.lookup_tag(tags, "600519.SH") == "staples"
    assert sectors.lookup_tag(tags, "BRK.B") == "financials"
    assert sectors.lookup_tag(tags, "000001") is None


async def test_load_cnhk_tags_skips_incomplete_result(monkeypatch):
    async def fake(market):
        return {"600519": "staples"}

    monkeypatch.setattr(sectors, "_fetch_cnhk_tags", fake)
    assert await sectors.load_sector_tags("cn", None) == {}


def test_every_native_sector_has_an_english_name():
    from app.services.quant_research.cnhk.sectors import HS_LEVEL1, NATIVE_SECTOR_EN, SW_LEVEL1

    missing = [n for n in (*SW_LEVEL1, *HS_LEVEL1) if not NATIVE_SECTOR_EN.get(n)]
    assert missing == []
    # 申万「公用事业」与恒生「公用事业」同名，共用一条；其余不应有未使用的多余条目
    assert set(NATIVE_SECTOR_EN) == set(SW_LEVEL1) | set(HS_LEVEL1)


class _TagCacheRedis:
    def __init__(self, store):
        self.store = store

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


async def test_stale_gics_tag_cache_is_discarded_and_refetched(monkeypatch):
    """改行业划分后 24 小时内的旧缓存（GICS key）对不上申万面板：必须丢弃重取，而不是原样返回。"""
    import json

    store = {f"{sectors.CNHK_TAGS_PREFIX}:cn": json.dumps({"600519": "staples", "000001": "financials"})}
    fresh = {f"{i:06d}": "电子" for i in range(1200)}

    async def fake(market):
        return fresh

    monkeypatch.setattr(sectors, "_fetch_cnhk_tags", fake)
    assert await sectors.load_sector_tags("cn", _TagCacheRedis(store)) == fresh
    assert json.loads(store[f"{sectors.CNHK_TAGS_PREFIX}:cn"]) == fresh      # 新结果覆盖旧缓存


async def test_valid_native_tag_cache_is_used(monkeypatch):
    import json

    cached = {"600519": "食品饮料", "000001": "银行"}
    store = {f"{sectors.CNHK_TAGS_PREFIX}:cn": json.dumps(cached, ensure_ascii=False)}

    async def boom(market):
        raise AssertionError("不应重取")

    monkeypatch.setattr(sectors, "_fetch_cnhk_tags", boom)
    assert await sectors.load_sector_tags("cn", _TagCacheRedis(store)) == cached
