"""市场结构 × 产业结构 gap 分析——确定性部分（市场摘要构建）单元测试。

analyze_structure_gap 依赖 LLM，不在单测覆盖；这里只验证喂给 LLM 的
【市场结构】摘要能忠实反映缠论结果，尤其是“未确认”标注要透传。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.gap import build_market_digest
from tests.services.chan.test_confirmations import _zigzag_bars


def test_digest_contains_symbol_and_trend():
    result = ChanAnalyzer().analyze("TEST", _zigzag_bars())
    digest = build_market_digest(result)

    assert "标的：TEST" in digest
    assert result.current_trend in digest


def test_digest_surfaces_pending_notes():
    """最右侧未确认结构必须出现在摘要里，供 LLM 据此降低确定性。"""
    result = ChanAnalyzer().analyze("TEST", _zigzag_bars())
    digest = build_market_digest(result)

    assert result.pending_notes, "构造数据应存在未确认结构"
    assert "最右侧未确认结构" in digest
    # 至少一条 pending_note 的内容被带入
    assert any(note in digest for note in result.pending_notes)


def test_digest_marks_unconfirmed_stroke():
    """最后一笔未确认时，摘要中应带“未确认”字样。"""
    result = ChanAnalyzer().analyze("TEST", _zigzag_bars())
    digest = build_market_digest(result)

    if result.strokes and not result.strokes[-1].confirmed:
        assert "未确认" in digest
