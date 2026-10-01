"""宏观驱动因素判定：方向、影响、大白话、数据不足。"""
from app.services.macro.drivers import US_DRIVERS, WINDOW, evaluate_driver

SPECS = {s.key: s for s in US_DRIVERS}


def _series(start: float, end: float, n: int = WINDOW + 1) -> list[tuple[str, float]]:
    step = (end - start) / (n - 1)
    return [(f"2026-09-{i + 1:02d}", start + step * i) for i in range(n)]


def test_rate_up_is_negative_in_basis_points():
    """利率上行：基点、偏负面。"""
    out = evaluate_driver(SPECS["us10y"], _series(4.00, 4.30))
    assert out.direction == "up"
    assert out.impact == "negative"
    assert out.change == 30.0  # 基点
    assert out.value == 4.3
    assert "承压" in out.text


def test_small_move_is_flat():
    """小幅变化算持平。"""
    out = evaluate_driver(SPECS["us10y"], _series(4.00, 4.05))
    assert out.direction == "flat"
    assert out.impact == "neutral"


def test_dollar_down_is_positive_and_hides_level():
    """美元走弱偏正面，不展示基金价格。"""
    out = evaluate_driver(SPECS["dollar"], _series(30.0, 29.0))
    assert out.direction == "down"
    assert out.impact == "positive"
    assert out.value is None  # 基金价格不当点位展示
    assert round(out.change or 0, 1) == -3.3


def test_inverted_curve_text():
    """利差倒挂时用倒挂文案。"""
    out = evaluate_driver(SPECS["curve"], _series(-0.10, -0.40))
    assert out.direction == "down"
    assert "倒挂" in out.text


def test_insufficient_and_empty_series():
    """数据不足 / 为空时不判方向。"""
    short = evaluate_driver(SPECS["vix"], _series(15, 20, n=5))
    assert short.direction is None and short.value == 20
    empty = evaluate_driver(SPECS["vix"], [])
    assert empty.direction is None and empty.value is None


def test_english_text():
    """英文文案。"""
    out = evaluate_driver(SPECS["vix"], _series(15, 25), lang="en")
    assert out.name == "VIX" and "Volatility rising" in out.text


def test_no_trading_words():
    """文案不出现买卖导向词和数据源名。"""
    banned = ("买", "卖", "加仓", "减仓", "抄底", "FMP", "UUP", "USO")
    for spec in US_DRIVERS:
        for text in (spec.text_up, spec.text_down, spec.text_flat):
            assert not any(b in text[0] for b in banned), text
