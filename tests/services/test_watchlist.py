"""自选股服务层单测。

展示名补全（纯函数）+ 分档加入上限（用假 AsyncSession 模拟两次 db.execute：
已存在检查 → 计数检查）。
"""
from __future__ import annotations

from app.models.watchlist import WatchlistItem
from app.services.watchlist import (
    TIER_LIMITS,
    WatchlistLimitExceeded,
    add_item,
    display_name,
    max_items_for,
)


class _FakeResult:
    """伪装 SQLAlchemy 的 Result：只实现 add_item 用到的 scalars().first() / scalar_one()。"""

    def __init__(self, *, first=None, scalar=None):
        self._first = first
        self._scalar = scalar

    def scalars(self):
        return self

    def first(self):
        return self._first

    def scalar_one(self):
        return self._scalar


class _FakeSession:
    """按调用顺序依次返回预设结果的假 AsyncSession，不接真数据库。"""

    def __init__(self, results):
        self._results = list(results)
        self.added: list = []
        self.committed = False

    async def execute(self, *_args, **_kwargs):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        pass


class TestAddItemLimit:
    async def test_raises_when_at_limit_free_tier(self):
        limit = TIER_LIMITS["free"]
        session = _FakeSession([
            _FakeResult(first=None),   # 未加过这只标的
            _FakeResult(scalar=limit),  # 已达免费档上限（1）
        ])
        try:
            await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL", tier="free")
            raise AssertionError("expected WatchlistLimitExceeded")
        except WatchlistLimitExceeded as e:
            assert e.limit == limit
        assert session.added == []
        assert not session.committed

    async def test_allows_when_below_limit(self):
        session = _FakeSession([
            _FakeResult(first=None),
            _FakeResult(scalar=TIER_LIMITS["basic"] - 1),
        ])
        item = await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL", tier="basic")
        assert item.symbol == "AAPL"
        assert session.added == [item]
        assert session.committed

    async def test_raises_when_at_limit_basic_tier(self):
        limit = TIER_LIMITS["basic"]
        session = _FakeSession([
            _FakeResult(first=None),
            _FakeResult(scalar=limit),
        ])
        try:
            await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL", tier="basic")
            raise AssertionError("expected WatchlistLimitExceeded")
        except WatchlistLimitExceeded as e:
            assert e.limit == limit

    async def test_premium_tier_never_limited(self):
        # 高级版不限：不该碰计数查询，只有一次「已存在」检查。
        session = _FakeSession([_FakeResult(first=None)])
        item = await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL", tier="premium")
        assert item.symbol == "AAPL"
        assert session.committed

    async def test_unknown_tier_falls_back_to_free(self):
        session = _FakeSession([
            _FakeResult(first=None),
            _FakeResult(scalar=TIER_LIMITS["free"]),
        ])
        try:
            await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL", tier="bogus")
            raise AssertionError("expected WatchlistLimitExceeded")
        except WatchlistLimitExceeded:
            pass

    async def test_default_tier_is_free(self):
        # 不传 tier（旧客户端/内部调用）按最保守的 free 处理。
        session = _FakeSession([
            _FakeResult(first=None),
            _FakeResult(scalar=TIER_LIMITS["free"]),
        ])
        try:
            await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL")
            raise AssertionError("expected WatchlistLimitExceeded")
        except WatchlistLimitExceeded:
            pass

    async def test_updating_existing_item_bypasses_limit(self):
        # 幂等更新走「已存在」分支，不会碰计数查询——达到上限也不该拦住改名。
        existing = WatchlistItem(user_id=1, market="us", symbol="AAPL", name="旧名字")
        session = _FakeSession([_FakeResult(first=existing)])
        item = await add_item(session, user_id=1, market="us", symbol="AAPL", name="苹果", tier="free")
        assert item is existing
        assert item.name == "苹果"
        assert session.committed


class TestMaxItemsFor:
    def test_free_is_one(self):
        assert max_items_for("free") == 1

    def test_basic_is_ten(self):
        assert max_items_for("basic") == 10

    def test_premium_is_unlimited(self):
        assert max_items_for("premium") is None

    def test_unknown_tier_falls_back_to_free(self):
        assert max_items_for("nonsense") == max_items_for("free")


class TestDisplayName:
    def test_keeps_real_stored_name(self):
        # 已经存了真名就原样保留，不覆盖
        assert display_name("hk", "2015", "理想汽车-W") == "理想汽车-W"

    def test_fills_name_when_stored_is_just_code(self):
        # 历史上只存了代码 → 用 curated 成分清单补中文名
        assert display_name("hk", "2015", "2015") == "理想汽车"
        assert display_name("us", "NVDA", "NVDA") == "英伟达"

    def test_fills_name_when_stored_empty(self):
        assert display_name("cn", "688981", "") == "中芯国际"

    def test_falls_back_to_code_when_not_in_universe(self):
        # 不在任何 curated 成分里（如 FIG）：补不到就回落代码本身，不报错
        assert display_name("us", "FIG", "FIG") == "FIG"
        assert display_name("us", "FIG", "") == "FIG"

    def test_stored_name_case_differs_from_code_kept(self):
        # 存的名字与代码大小写不同但语义就是代码——仍按「等于代码」处理去补全
        assert display_name("us", "NVDA", "nvda") == "英伟达"


# ---- 示例自选：每个用户默认送美/A/港市值龙头各一只，不占名额、可删、删了不再补 ----

from app.services.watchlist import SAMPLE_ITEMS, remove_item, samples_to_seed  # noqa: E402


def _item(market, symbol, *, is_sample=False, hidden=False):
    return WatchlistItem(user_id=1, market=market, symbol=symbol, name=symbol,
                         is_sample=is_sample, hidden=hidden)


class _DelSession(_FakeSession):
    def __init__(self, results):
        super().__init__(results)
        self.deleted: list = []

    async def delete(self, obj):
        self.deleted.append(obj)


class TestSamplesToSeed:
    def test_new_user_gets_all_three(self):
        assert [(m, s) for m, s, _ in samples_to_seed([])] == [(m, s) for m, s, _ in SAMPLE_ITEMS]

    def test_defaults_are_nvda_moutai_tencent(self):
        assert {(m, s) for m, s, _ in SAMPLE_ITEMS} == {("us", "NVDA"), ("cn", "600519"), ("hk", "0700")}

    def test_seeded_once_even_if_all_deleted(self):
        rows = [_item(m, s, is_sample=True, hidden=True) for m, s, _ in SAMPLE_ITEMS]
        assert samples_to_seed(rows) == []

    def test_skips_symbol_user_already_follows(self):
        seeded = samples_to_seed([_item("us", "NVDA")])
        assert [(m, s) for m, s, _ in seeded] == [("cn", "600519"), ("hk", "0700")]


class TestSampleRemoveAndReadd:
    async def test_removing_sample_hides_instead_of_deleting(self):
        sample = _item("us", "NVDA", is_sample=True)
        session = _DelSession([_FakeResult(first=sample)])
        assert await remove_item(session, 1, "us", "NVDA") is True
        assert sample.hidden is True
        assert session.deleted == []

    async def test_removing_own_item_deletes(self):
        own = _item("us", "AAPL")
        session = _DelSession([_FakeResult(first=own)])
        assert await remove_item(session, 1, "us", "AAPL") is True
        assert session.deleted == [own]

    async def test_readding_hidden_sample_becomes_own_item(self):
        hidden = _item("us", "NVDA", is_sample=True, hidden=True)
        session = _FakeSession([_FakeResult(first=hidden), _FakeResult(scalar=0)])
        item = await add_item(session, 1, "us", "NVDA", "英伟达", tier="free")
        assert item.hidden is False and item.is_sample is False

    async def test_readding_hidden_sample_respects_limit(self):
        hidden = _item("us", "NVDA", is_sample=True, hidden=True)
        session = _FakeSession([_FakeResult(first=hidden), _FakeResult(scalar=TIER_LIMITS["free"])])
        try:
            await add_item(session, 1, "us", "NVDA", "英伟达", tier="free")
        except WatchlistLimitExceeded:
            pass
        else:
            raise AssertionError("重新加入已删的示例股会变成自己的自选，应当受名额限制")
        assert hidden.hidden is True
