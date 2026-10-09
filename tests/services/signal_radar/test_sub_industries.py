"""名单的子行业标签：美股 GICS 子行业（中文名对照）、A 股申万二级、港股恒生二级。"""
import json

from app.services.signal_radar import sub_industries as si

_WIKI_HTML = """
<table>
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>
<tr><td>NVDA</td><td>Nvidia</td><td>Information Technology</td><td>Semiconductors</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td></tr>
<tr><td>bad sym</td><td>x</td><td>Energy</td><td>Integrated Oil &amp; Gas</td></tr>
</table>
"""


def test_parse_wiki_sub_table():
    """解析维基成分表的 GICS Sub-Industry 列；代码点号换连字符，异常代码丢弃。"""
    assert si.parse_sub_table(_WIKI_HTML) == {"NVDA": "Semiconductors", "BRK-B": "Multi-Sector Holdings"}


def test_display_name_by_market_and_lang():
    """美股中文界面用对照表，英文界面原名；A 股去掉申万二级的「Ⅱ」后缀；港股原样。"""
    assert si.display_name("us", "Semiconductors", "zh") == "半导体"
    assert si.display_name("us", "Semiconductors", "en") == "Semiconductors"
    assert si.display_name("us", "Something New", "zh") == "Something New"   # 没有对照的退回原名
    assert si.display_name("cn", "林业Ⅱ", "zh") == "林业"
    assert si.display_name("hk", "半导体", "zh") == "半导体"


def test_zh_table_covers_all_gics_sub_industries():
    """对照表覆盖维基标普 1500 上出现过的全部 GICS 子行业（2026-10-09 实测 154 个），且没有空名。"""
    assert len(si.GICS_SUB_ZH) >= 154
    assert all(v.strip() for v in si.GICS_SUB_ZH.values())
    for name in ("Regional Banks", "Application Software", "Semiconductor Materials & Equipment", "Water Utilities"):
        assert name in si.GICS_SUB_ZH


def test_cnhk_tags_only_mapped_industries():
    """A 股 / 港股只收已映射到一级行业的东财行业名（映射表外的不打子行业）。"""
    class M:
        def __init__(self, industry):
            self.industry = industry

    cn = si.cnhk_sub_tags("cn", {"600000": M("银行Ⅱ"), "000001": M("不存在的行业"), "000002": M(None)})
    assert cn == {"600000": "银行Ⅱ"}


class _FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):
        self.kv[key] = value
        self.ttl[key] = ex
        return True


async def test_load_sub_tags_caches_with_ttl(monkeypatch):
    """取一次后写 Redis（带 TTL），第二次直接读缓存。"""
    calls = {"n": 0}

    async def fake_fetch(market):
        calls["n"] += 1
        return {"NVDA": "Semiconductors"}

    monkeypatch.setattr(si, "_fetch", fake_fetch)
    monkeypatch.setattr(si, "_MIN_TAGS", {"us": 1, "cn": 1, "hk": 1})
    redis = _FakeRedis()
    assert await si.load_sub_tags("us", redis) == {"NVDA": "Semiconductors"}   # type: ignore[arg-type]
    assert await si.load_sub_tags("us", redis) == {"NVDA": "Semiconductors"}   # type: ignore[arg-type]
    assert calls["n"] == 1
    key = next(iter(redis.kv))
    assert json.loads(redis.kv[key]) == {"NVDA": "Semiconductors"} and redis.ttl[key]


async def test_load_sub_tags_incomplete_not_cached(monkeypatch):
    """取回过少视为残缺：照样返回给这次请求用，但不缓存。"""
    async def fake_fetch(market):
        return {"NVDA": "Semiconductors"}

    monkeypatch.setattr(si, "_fetch", fake_fetch)
    redis = _FakeRedis()
    assert await si.load_sub_tags("us", redis) == {"NVDA": "Semiconductors"}   # type: ignore[arg-type]
    assert redis.kv == {}


async def test_load_sub_tags_failure_returns_empty(monkeypatch):
    """取数失败返回空，名单照常（只是没有子行业）。"""
    async def boom(market):
        raise RuntimeError("down")

    monkeypatch.setattr(si, "_fetch", boom)
    assert await si.load_sub_tags("us", _FakeRedis()) == {}   # type: ignore[arg-type]
