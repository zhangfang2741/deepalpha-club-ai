"""准确率口径（方向 + 时限）测试。"""

import pytest

from app.models.report import (
    DIRECTION_BEARISH,
    DIRECTION_BULLISH,
    DIRECTION_NEUTRAL,
)
from app.services.reports.accuracy import (
    OutcomeSample,
    compute_analyst_accuracy,
    compute_return_pct,
    evaluate_direction,
    horizon_end_date,
    is_hit,
)


def test_horizon_end_date():
    assert horizon_end_date("2026-01-01", 30) == "2026-01-31"


def test_compute_return_pct():
    assert compute_return_pct(100.0, 110.0) == pytest.approx(10.0)
    assert compute_return_pct(100.0, 90.0) == pytest.approx(-10.0)


def test_compute_return_pct_rejects_nonpositive_mark():
    with pytest.raises(ValueError):
        compute_return_pct(0.0, 10.0)


def test_bullish_hit():
    # 看多：涨即命中（默认门槛 0）
    ret, hit = evaluate_direction(DIRECTION_BULLISH, 100.0, 105.0)
    assert ret == pytest.approx(5.0)
    assert hit is True
    # 跌则未命中
    _, hit2 = evaluate_direction(DIRECTION_BULLISH, 100.0, 95.0)
    assert hit2 is False


def test_bearish_hit():
    _, hit = evaluate_direction(DIRECTION_BEARISH, 100.0, 92.0)
    assert hit is True
    _, hit2 = evaluate_direction(DIRECTION_BEARISH, 100.0, 108.0)
    assert hit2 is False


def test_neutral_band():
    # 中性：涨跌幅绝对值不超过带宽（默认 3%）算命中
    assert is_hit(DIRECTION_NEUTRAL, 2.0) is True
    assert is_hit(DIRECTION_NEUTRAL, -2.9) is True
    assert is_hit(DIRECTION_NEUTRAL, 4.0) is False


def test_hit_threshold_raises_bar():
    # 门槛设为 5%：涨 3% 不算看多命中
    assert is_hit(DIRECTION_BULLISH, 3.0, hit_threshold_pct=5.0) is False
    assert is_hit(DIRECTION_BULLISH, 6.0, hit_threshold_pct=5.0) is True


def test_unknown_direction_raises():
    with pytest.raises(ValueError):
        is_hit("SIDEWAYS", 1.0)


def test_compute_analyst_accuracy_ignores_unresolved():
    samples = [
        OutcomeSample(is_correct=True, actual_return_pct=10.0),
        OutcomeSample(is_correct=False, actual_return_pct=-5.0),
        OutcomeSample(is_correct=True, actual_return_pct=8.0),
        OutcomeSample(is_correct=None, actual_return_pct=None),  # 未到期，忽略
    ]
    acc = compute_analyst_accuracy(samples)
    assert acc.resolved_count == 3
    assert acc.correct_count == 2
    assert acc.accuracy == pytest.approx(2 / 3)
    assert acc.avg_return_pct == pytest.approx((10.0 - 5.0 + 8.0) / 3)


def test_compute_analyst_accuracy_empty():
    acc = compute_analyst_accuracy([])
    assert acc.resolved_count == 0
    assert acc.accuracy is None
    assert acc.avg_return_pct is None
