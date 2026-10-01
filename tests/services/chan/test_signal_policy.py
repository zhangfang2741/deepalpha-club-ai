"""买卖点口径注册表：统一接口 + 宽松 / 严格两套实现。"""
from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.signal_policy import DEFAULT_MODE, SIGNAL_POLICIES, get_policy, normalize_mode
from tests.services.chan.test_signals import _decaying_downtrend_bars


def test_registry_has_loose_default_and_strict():
    assert DEFAULT_MODE == "loose"
    assert {"loose", "strict"} <= set(SIGNAL_POLICIES)
    for name, p in SIGNAL_POLICIES.items():
        assert p.name == name and p.version and p.label_zh and p.label_en and "first" in p.czsc_families


def test_versions_are_unique():
    """雷达缓存键按版本隔离，不同口径绝不能共用版本号。"""
    versions = [p.version for p in SIGNAL_POLICIES.values()]
    assert len(versions) == len(set(versions))


def test_unknown_mode_falls_back_to_default():
    assert get_policy(None).name == DEFAULT_MODE
    assert get_policy("no-such-mode").name == DEFAULT_MODE
    assert normalize_mode("strict") == "strict"


def test_loose_keeps_last_stroke_signal_as_unconfirmed(monkeypatch):
    """宽松：最后一笔上的信号照常输出（标未确认），不单列候选；严格：移入候选。

    只检验候选拆分：让严格口径的 c/b 背驰判定「不能判定」、退回 czsc 笔级事件（合成数据按原文不背驰）。
    """
    monkeypatch.setattr("app.services.chan.signals._trend_leg_divergence", lambda *a, **k: (False, None))
    bars = _decaying_downtrend_bars()
    loose = ChanAnalyzer().analyze("DN", bars, mode="loose")
    strict = ChanAnalyzer().analyze("DN", bars, mode="strict")
    assert loose.candidate_signals == []
    assert any(not s.confirmed for s in loose.signals)
    assert all(s.confirmed for s in strict.signals)
    assert strict.candidate_signals


def test_default_analyze_is_loose():
    bars = _decaying_downtrend_bars()
    default = ChanAnalyzer().analyze("DN", bars)
    loose = ChanAnalyzer().analyze("DN", bars, mode="loose")
    assert [(s.type, s.time) for s in default.signals] == [(s.type, s.time) for s in loose.signals]
