"""自选股服务层单测。

展示名补全（纯函数）+ 加入上限（用假 AsyncSession 模拟两次 db.execute：
已存在检查 → 计数检查）。
"""
from __future__ import annotations

from app.models.watchlist import WatchlistItem
from app.services.watchlist import MAX_ITEMS, WatchlistLimitExceeded, add_item, display_name


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
    async def test_raises_when_at_limit(self):
        session = _FakeSession([
            _FakeResult(first=None),        # 未加过这只标的
            _FakeResult(scalar=MAX_ITEMS),  # 已有 MAX_ITEMS 条，达到上限
        ])
        try:
            await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL")
            raise AssertionError("expected WatchlistLimitExceeded")
        except WatchlistLimitExceeded:
            pass
        assert session.added == []
        assert not session.committed

    async def test_allows_when_below_limit(self):
        session = _FakeSession([
            _FakeResult(first=None),
            _FakeResult(scalar=MAX_ITEMS - 1),
        ])
        item = await add_item(session, user_id=1, market="us", symbol="AAPL", name="AAPL")
        assert item.symbol == "AAPL"
        assert session.added == [item]
        assert session.committed

    async def test_updating_existing_item_bypasses_limit(self):
        # 幂等更新走「已存在」分支，不会碰计数查询——达到上限也不该拦住改名。
        existing = WatchlistItem(user_id=1, market="us", symbol="AAPL", name="旧名字")
        session = _FakeSession([_FakeResult(first=existing)])
        item = await add_item(session, user_id=1, market="us", symbol="AAPL", name="苹果")
        assert item is existing
        assert item.name == "苹果"
        assert session.committed


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
