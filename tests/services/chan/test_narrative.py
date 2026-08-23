"""大白话形态解读测试。"""
from __future__ import annotations

import math

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.narrative import _volume_readout


def _bars(closes: list[float], vols: list[float]) -> list[dict]:
    """由收盘价与成交量构造最小 bars（OHLC 围绕 close 造一个小范围）。"""
    out = []
    for i, (c, v) in enumerate(zip(closes, vols, strict=True)):
        out.append({
            "time": f"2026-01-{i + 1:02d}",
            "open": c - 0.1, "high": c + 0.2, "low": c - 0.2, "close": c, "volume": v,
        })
    return out


class TestVolumeReadout:
    def test_放量上涨(self):
        closes = [10.0] * 30 + [10.5, 11.0, 11.5, 12.0, 12.5]  # 近端明显上涨
        vols = [100.0] * 30 + [300.0] * 5                       # 近端放量
        label, sentence = _volume_readout(_bars(closes, vols), "zh")
        assert label == "放量"
        assert "放量上涨" in sentence

    def test_缩量下跌(self):
        closes = [12.0] * 30 + [11.5, 11.0, 10.5, 10.0, 9.5]
        vols = [200.0] * 30 + [40.0] * 5                        # 近端缩量
        label, sentence = _volume_readout(_bars(closes, vols), "zh")
        assert label == "缩量"
        assert "抛压趋缓" in sentence or "缩量下跌" in sentence

    def test_数据不足返回None(self):
        assert _volume_readout(_bars([10.0] * 5, [100.0] * 5), "zh") is None

    def test_全零成交量返回None(self):
        assert _volume_readout(_bars([10.0] * 20, [0.0] * 20), "zh") is None


class TestBuildNarrative:
    def test_笔不足时返回None(self):
        """结构没成形（笔 < 3）时不产出解读。"""
        bars = _bars([10.0] * 12, [100.0] * 12)
        result = ChanAnalyzer().analyze("TEST", bars)
        assert result.narrative is None

    def test_有结构时产出完整解读(self):
        """给一段震荡上行的行情，应产出非空的阶段/概括/分条解读。"""
        # 造 120 根锯齿上行：既能形成多笔结构，又有明确趋势
        closes = [20.0 + i * 0.15 + math.sin(i / 3) * 2 for i in range(120)]
        vols = [100.0 + (i % 7) * 20 for i in range(120)]
        result = ChanAnalyzer().analyze("TEST", _bars(closes, vols))

        n = result.narrative
        assert n is not None
        assert n.phase and n.phase_label
        assert n.headline
        assert n.details  # 至少有趋势/位置/量价之一
        # 解读里应包含量价这一维度
        assert any("量" in d for d in n.details)

    def test_英文输出(self):
        """lang=en：解读/趋势/建议应输出英文（无中文字符）。"""
        closes = [20.0 + i * 0.15 + math.sin(i / 3) * 2 for i in range(120)]
        vols = [100.0 + (i % 7) * 20 for i in range(120)]
        result = ChanAnalyzer().analyze("TEST", _bars(closes, vols), lang="en")

        def _has_cjk(s: str) -> bool:
            return any("一" <= ch <= "鿿" for ch in s)

        assert result.narrative is not None
        assert not _has_cjk(result.narrative.headline)
        assert not _has_cjk(result.current_trend)
        assert not _has_cjk(result.recommendation.action_label)
        for line in result.narrative.details + result.recommendation.reasons + result.recommendation.caveats:
            assert not _has_cjk(line), line
