"""接口 SignalOut 的日期字段：详情页与雷达气泡必须用同一个展示日。"""
from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.signals import Signal
from app.services.chan.sub_level_service import signal_out
from app.services.signal_radar import service as radar
from tests.services.chan.test_signals import _decaying_downtrend_bars


def _sig(time: str, detected: str | None) -> Signal:
    sig = Signal(type="buy1", time=time, price=10.0, strength="medium", divergence=None,
                 description="", confirmed=True, lang="zh")
    sig.detected_time = detected
    return sig


def test_signal_out_exposes_detected_time() -> None:
    out = signal_out(_sig("2026-09-20", "2026-09-23"))
    assert out.time == "2026-09-20"  # 图上标记仍落在笔终点（极值 K 线）
    assert out.detected_time == "2026-09-23"


def test_signal_out_detected_time_falls_back_to_stroke_end() -> None:
    assert signal_out(_sig("2026-09-20", None)).detected_time == "2026-09-20"


def test_detail_and_radar_use_the_same_display_date() -> None:
    """同一次分析：详情页 detected_time 与雷达气泡 date 逐条相同。"""
    result = ChanAnalyzer().analyze("X", _decaying_downtrend_bars(), mode="loose")
    assert result.signals
    detail = sorted(signal_out(s).detected_time for s in result.signals)
    bubbles = sorted(r.date for r in radar.build_signal_history("X", "测试", result))
    assert detail == bubbles


def test_signal_out_keeps_intraday_time() -> None:
    """次级别 30 分钟线的展示时刻带时分，不能被截成纯日期。"""
    assert signal_out(_sig("2026-09-24 10:30", "2026-09-24 14:00")).detected_time == "2026-09-24 14:00"
