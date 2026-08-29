"""技术形态倾向（Recommendation）的多因子加权测试。

改造前 bias 只由「末笔方向 × 背驰」这一个维度决定，于是页面上出现过
chip 写「偏空」、而正下方「依据」里写着「多头占优、大级别趋势偏多」的
自相矛盾。这里锁定的不变量是：**结论必须与全部因子的加权和同向**，
且背驰只作为扣分项参与，不再单独把方向掀翻。
"""
from __future__ import annotations

import math

import pytest

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.bias import BIAS_THRESHOLD
from app.services.chan.divergence import DivergenceResult


def _bars(closes: list[float], vols: list[float]) -> list[dict]:
    return [
        {
            "time": f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d}",
            "open": c - 0.1, "high": c + 0.2, "low": c - 0.2, "close": c, "volume": v,
        }
        for i, (c, v) in enumerate(zip(closes, vols, strict=True))
    ]


def _uptrend_bars(n: int = 120) -> list[dict]:
    """锯齿上行：既能形成多笔结构，又有明确的多头方向。"""
    closes = [20.0 + i * 0.15 + math.sin(i / 3) * 2 for i in range(n)]
    return _bars(closes, [100.0 + (i % 7) * 20 for i in range(n)])


def _downtrend_bars(n: int = 120) -> list[dict]:
    closes = [40.0 - i * 0.15 + math.sin(i / 3) * 2 for i in range(n)]
    return _bars(closes, [100.0 + (i % 7) * 20 for i in range(n)])


def _clear_divergences(result) -> None:
    for dv in result.divergences:
        dv.is_diverged = False


def _set_only_divergence(result, direction: str) -> None:
    """清掉所有背驰，只在最后一根指定方向的笔上标记背驰（构造确定性场景）。"""
    _clear_divergences(result)
    n = min(len(result.strokes), len(result.divergences))
    for i in range(n - 1, -1, -1):
        if result.strokes[i].direction == direction:
            result.divergences[i] = DivergenceResult(
                is_diverged=True, type="trend", strength="strong",
                area_ratio=0.6, description="test divergence",
            )
            return
    raise AssertionError(f"行情里没有 {direction} 方向的笔，测试用例不成立")


class TestBiasWeighting:
    def test_分数等于各因子加总(self):
        bars = _uptrend_bars()
        rec = ChanAnalyzer().analyze("TEST", bars).recommendation
        assert rec is not None
        assert rec.factors, "应逐项记录参与打分的因子"
        assert rec.score == pytest.approx(sum(f.score for f in rec.factors))

    @pytest.mark.parametrize("bars", [_uptrend_bars(), _downtrend_bars()])
    def test_bias与分数符号一致(self, bars):
        rec = ChanAnalyzer().analyze("TEST", bars).recommendation
        assert rec is not None
        if rec.bias == "bullish":
            assert rec.score >= BIAS_THRESHOLD
        elif rec.bias == "bearish":
            assert rec.score <= -BIAS_THRESHOLD
        else:
            assert abs(rec.score) < BIAS_THRESHOLD

    def test_顶背驰只扣分不直接翻空(self):
        """这是用户报的那个冲突：上涨动能减弱 ≠ 偏空。"""
        bars = _uptrend_bars()
        a = ChanAnalyzer()
        result = a.analyze("TEST", bars)

        _clear_divergences(result)
        base = a._build_recommendation(result, bars)

        _set_only_divergence(result, "up")
        after = a._build_recommendation(result, bars)

        # 顶背驰是固定的扣分项，而不是方向开关
        assert after.score == pytest.approx(base.score - 1.5)
        if base.score - 1.5 >= BIAS_THRESHOLD:
            assert after.bias == "bullish"
        # 动能衰减仍要说出来，只是降级为标签后缀
        assert "动能转弱" in after.action_label

    def test_底背驰只加分不直接翻多(self):
        bars = _downtrend_bars()
        a = ChanAnalyzer()
        result = a.analyze("TEST", bars)

        _clear_divergences(result)
        base = a._build_recommendation(result, bars)

        _set_only_divergence(result, "down")
        after = a._build_recommendation(result, bars)

        assert after.score == pytest.approx(base.score + 1.5)
        if base.score + 1.5 <= -BIAS_THRESHOLD:
            assert after.bias == "bearish"
        assert "动能转弱" in after.action_label


class TestReasons:
    def test_首条是因子统计(self):
        """依据列表要先说明自己是被加权的。

        结论与依据合成一张卡后，「偏多」下面挂着一条「空头占优」，
        没有这句开场白就仍然像自相矛盾。
        """
        rec = ChanAnalyzer().analyze("TEST", _uptrend_bars()).recommendation
        assert rec is not None
        head = rec.reasons[0]
        assert "综合" in head and "因子" in head
        assert str(len(rec.factors)) in head

    def test_依据覆盖量价维度(self):
        """量价原本只在「形态解读」那张卡里，两卡合并后不能丢。"""
        rec = ChanAnalyzer().analyze("TEST", _uptrend_bars()).recommendation
        assert rec is not None
        assert any("量" in r for r in rec.reasons)

    def test_每条依据都对应一个因子(self):
        rec = ChanAnalyzer().analyze("TEST", _uptrend_bars()).recommendation
        assert rec is not None
        # reasons = 1 条统计汇总 + 各因子文案
        assert rec.reasons[1:] == [f.text for f in rec.factors]

    def test_标签不复述形态解读的阶段标签(self):
        """两张卡合并前，phase_label 与 action_label 撞车（都叫「上涨动能减弱」）。"""
        result = ChanAnalyzer().analyze("TEST", _uptrend_bars())
        assert result.narrative is not None and result.recommendation is not None
        assert result.narrative.phase_label not in result.recommendation.action_label


class TestEnglish:
    def test_英文输出无中文(self):
        result = ChanAnalyzer().analyze("TEST", _uptrend_bars(), lang="en")
        rec = result.recommendation
        assert rec is not None

        def _has_cjk(s: str) -> bool:
            return any("一" <= ch <= "鿿" for ch in s)

        assert not _has_cjk(rec.action_label)
        for line in rec.reasons + rec.caveats:
            assert not _has_cjk(line), line
