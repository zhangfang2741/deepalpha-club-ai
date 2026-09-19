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
