"""自选股展示名补全逻辑单测（纯函数，无 IO）。"""
from __future__ import annotations

from app.services.watchlist import display_name


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
