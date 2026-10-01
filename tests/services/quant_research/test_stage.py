"""阶段判定：营收增速为主轴、经营现金流为辅（Morningstar 股票类型思路映射到五阶段）。"""

from dataclasses import replace

import pytest

from app.services.quant_research.stage import classify_stage, stage_of
from tests.services.quant_research.fixtures import load_inputs


@pytest.mark.parametrize(
    ("cfo", "g1", "g3", "expected"),
    [
        # 高增长：同比 ≥ 15% 且 3 年复合 ≥ 10%（不足 3 年只看同比）
        (1, 0.43, None, "growth"),     # FIG：上市不满 3 年，经营现金流为正
        (1, 0.83, 1.10, "growth"),     # NVDA
        (-1, 0.78, 0.76, "intro"),     # 高增长但经营现金流为负
        (0, 0.20, None, "intro"),      # 零值归非正
        (1, 0.25, 0.085, "mature"),    # BA：停产后恢复，3 年复合不够 → 不算高增长
        (1, 0.149, 0.30, "mature"),    # 同比不足 15%
        # 平稳
        (1, 0.03, 0.02, "mature"),
        (-1, 0.03, 0.02, "shakeout"),
        # 萎缩：同比 ≤ −5%
        (1, -0.05, -0.02, "shakeout"),
        (-1, -0.27, -0.40, "decline"),
        (1, -0.049, None, "mature"),
    ],
)
def test_classify(cfo, g1, g3, expected):
    assert classify_stage(cfo, g1, g3) == expected


def test_missing_returns_none():
    assert classify_stage(None, 0.2, 0.2) is None
    assert classify_stage(1, None, 0.2) is None


def _quarters(revenues: list[float]) -> list[dict]:
    """新 → 旧的季度营收。"""
    return [{"date": f"2026-{i:02d}", "revenue": r} for i, r in enumerate(revenues)]


def test_no_revenue_base_with_cash_burn_is_intro():
    """营收基数为零（如尚无收入的生物科技）且在烧钱 → 初创期。"""
    inp = load_inputs("NVDA")
    cash = [dict(q, netCashProvidedByOperatingActivities=-10) for q in inp.quarters_cash]
    inp = replace(inp, quarters_income=_quarters([5, 0, 0, 0, 0, 0, 0, 0]), quarters_cash=cash)
    info = stage_of(inp, None, None)
    assert info is not None and info.key == "intro"


def test_fixtures_have_stage():
    info = stage_of(load_inputs("NVDA"), 0.83, 1.10)
    assert info is not None
    assert info.key == "growth"
    assert info.operating > 0
    assert info.revenue_growth == 0.83 and info.revenue_cagr_3y == 1.10
    assert info.unprofitable is False
    for s in ("O", "XOM"):
        assert stage_of(load_inputs(s), 0.05, 0.03) is not None


def test_financials_have_no_stage():
    assert stage_of(load_inputs("JPM"), 0.1, 0.1) is None


def test_stage_ios_rules_match_thresholds():
    """App 端阶段规则文案里的门槛与后端常量一致。"""
    from pathlib import Path

    from app.services.quant_research.stage import GROWTH_CAGR3_MIN, GROWTH_YOY_MIN, SHRINK_YOY_MAX

    root = Path(__file__).resolve().parents[3]
    src = (root / "ios/DeepAlphaChan/Models/QuantLifecycleStage.swift").read_text()
    rules = src[src.index("var rule: String"):]
    assert f"营收同比 ≥ {GROWTH_YOY_MIN:.0%}" in rules
    assert f"3 年复合 ≥ {GROWTH_CAGR3_MIN:.0%}" in rules
    assert f"营收同比 ≤ −{-SHRINK_YOY_MAX:.0%}" in rules
    assert f"−{-SHRINK_YOY_MAX:.0%} ~ {GROWTH_YOY_MIN:.0%}" in rules
