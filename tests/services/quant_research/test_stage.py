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


# ---------- 阶段权重与滞回 ----------

def test_stage_weights_cover_every_stage_and_sum_to_one():
    from app.services.quant_research.metrics import DIMENSIONS
    from app.services.quant_research.stage import STAGE_NAMES, STAGE_WEIGHTS

    assert set(STAGE_WEIGHTS) == set(STAGE_NAMES) | {None}
    for stage, row in STAGE_WEIGHTS.items():
        assert set(row) == set(DIMENSIONS), stage
        assert sum(row.values()) == pytest.approx(1.0), stage
        assert all(w > 0 for w in row.values()), stage


def test_weights_for_unknown_stage_is_equal():
    from app.services.quant_research.metrics import DIMENSIONS
    from app.services.quant_research.stage import weights_for

    w = weights_for(None)
    assert all(v == pytest.approx(1 / len(DIMENSIONS)) for v in w.values())
    assert weights_for("nonexistent") == w


def test_growth_stage_leans_on_growth_not_valuation():
    from app.services.quant_research.stage import weights_for

    g, m = weights_for("growth"), weights_for("mature")
    assert g["growth"] > m["growth"] and g["valuation"] < m["valuation"]


def test_every_stage_gives_stability_a_veto():
    """财务稳健在每个阶段的权重都不低于一票否决门槛：偿债 / 现金出问题时综合等级必须能被压住。"""
    from app.services.quant_research.scoring import CAP_MIN_WEIGHT
    from app.services.quant_research.stage import STAGE_WEIGHTS

    for stage, row in STAGE_WEIGHTS.items():
        assert row["stability"] >= CAP_MIN_WEIGHT - 1e-9, stage


def test_growth_stage_valuation_cannot_veto():
    """成长期估值权重低于否决门槛：高增速公司估值贵不再一票封顶（本次改动的初衷）。"""
    from app.services.quant_research.scoring import CAP_MIN_WEIGHT
    from app.services.quant_research.stage import STAGE_WEIGHTS

    assert STAGE_WEIGHTS["growth"]["valuation"] < CAP_MIN_WEIGHT
    assert STAGE_WEIGHTS["intro"]["valuation"] < CAP_MIN_WEIGHT


# ---------- 连续权重（营收增速 × 现金流利润率双向插值，不再按阶段档位跳变） ----------

def _rows():
    from app.services.quant_research.stage import STAGE_WEIGHTS
    return STAGE_WEIGHTS


def _close(a, b):
    return all(abs(a[k] - b[k]) < 1e-9 for k in b)


def test_blend_matches_stage_rows_far_from_thresholds():
    from app.services.quant_research.stage import blend_weights

    r = _rows()
    assert _close(blend_weights(0.30, 0.20, 0.20), r["growth"])      # 高增长 + 现金流为正
    assert _close(blend_weights(0.30, 0.20, -0.20), r["intro"])      # 高增长 + 烧钱
    assert _close(blend_weights(0.05, 0.05, 0.20), r["mature"])
    assert _close(blend_weights(0.05, 0.05, -0.20), r["shakeout"])
    assert _close(blend_weights(-0.15, -0.05, 0.20), r["shakeout"])  # 萎缩但现金流为正
    assert _close(blend_weights(-0.15, -0.05, -0.20), r["decline"])


def test_blend_is_midway_at_the_thresholds():
    from app.services.quant_research.stage import blend_weights

    r = _rows()
    mid = blend_weights(0.15, None, 0.20)                            # 恰在 15% 门槛：成长与成熟各半
    assert _close(mid, {k: (r["growth"][k] + r["mature"][k]) / 2 for k in r["growth"]})
    cash_mid = blend_weights(0.30, 0.20, 0.0)                        # 现金流利润率 0：成长与初创各半
    assert _close(cash_mid, {k: (r["growth"][k] + r["intro"][k]) / 2 for k in r["growth"]})


def test_blend_weights_sum_to_one_and_have_no_cliffs():
    """整个定义域上权重和为 1，且增速 / 现金流利润率每动 0.1 个点，任一维度权重变化都很小（旧档位制在门槛处会整行跳 10+ 个点）。"""
    from app.services.quant_research.stage import blend_weights

    prev = None
    for i in range(-300, 501):                                       # 营收同比 −30% ~ +50%
        g = i / 1000
        w = blend_weights(g, g, 0.10)
        assert sum(w.values()) == pytest.approx(1.0)
        if prev is not None:
            assert max(abs(w[k] - prev[k]) for k in w) < 0.01, g
        prev = w
    prev = None
    for i in range(-100, 101):                                       # 现金流利润率 −10% ~ +10%
        w = blend_weights(0.30, 0.20, i / 1000)
        assert sum(w.values()) == pytest.approx(1.0)
        if prev is not None:
            assert max(abs(w[k] - prev[k]) for k in w) < 0.01, i
        prev = w


def test_three_year_cagr_discounts_high_growth():
    """同比很高但 3 年复合不足（如停产后复产）：不能按高增长给权重。"""
    from app.services.quant_research.stage import blend_weights

    assert _close(blend_weights(0.30, 0.0, 0.20), _rows()["mature"])
    assert blend_weights(0.30, 0.10, 0.20)["growth"] > _rows()["mature"]["growth"]   # 刚到门槛：介于两者之间


def test_stability_keeps_veto_weight_everywhere():
    from app.services.quant_research.scoring import CAP_MIN_WEIGHT
    from app.services.quant_research.stage import blend_weights

    for g in (-0.3, -0.05, 0.0, 0.1, 0.15, 0.4):
        for c in (-0.2, 0.0, 0.2):
            assert blend_weights(g, g, c)["stability"] >= CAP_MIN_WEIGHT - 1e-9


def test_stage_of_carries_blended_weights():
    info = stage_of(load_inputs("NVDA"), 0.83, 1.10)
    assert info is not None and info.key == "growth"
    assert _close(info.weights, _rows()["growth"])                   # NVDA 增速 / 现金流都远离门槛 = 整行
    near = stage_of(load_inputs("NVDA"), 0.15, None)
    assert near is not None and near.weights["growth"] < _rows()["growth"]["growth"]
    assert stage_of(load_inputs("JPM"), 0.1, 0.1) is None            # 金融股没有阶段 → 等权由调用方处理
