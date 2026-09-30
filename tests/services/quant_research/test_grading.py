from app.services.quant_research.grading import BANDS, grade_for, grade_with_hysteresis, percentile_of


def test_bands_edges():
    assert grade_for(93) == "A+" and grade_for(92.99) == "A"
    assert grade_for(20) == "D-" and grade_for(19.99) == "F"
    assert grade_for(0) == "F" and grade_for(100) == "A+"
    assert [g for _, g in BANDS][:3] == ["A+", "A", "A-"]
    assert len(BANDS) == 13


def test_hysteresis_keeps_previous_within_margin():
    # 旧等级 B 的区间是 [66, 73)，两侧各放宽 2 分
    assert grade_with_hysteresis(64.5, "B") == "B"
    assert grade_with_hysteresis(64.0, "B") == "B-"
    assert grade_with_hysteresis(75.5, "B") == "B+"
    assert grade_with_hysteresis(74.9, "B") == "B"
    assert grade_with_hysteresis(50, None) == "C"
    assert grade_with_hysteresis(99, "A+") == "A+"
    assert grade_with_hysteresis(1, "F") == "F"
    assert grade_with_hysteresis(21.5, "F") == "F"
    assert grade_with_hysteresis(22.0, "F") == "D-"


def test_percentile_higher_better_and_lower_better():
    values = [1, 2, 3, 4, 5]
    assert percentile_of(5, values, lower_better=False) == 100.0
    assert percentile_of(1, values, lower_better=True) == 100.0
    assert percentile_of(3, values, lower_better=False) == 60.0
    assert percentile_of(5, values, lower_better=True) == 20.0


def test_percentile_ties_and_out_of_sample():
    assert percentile_of(2, [2, 2, 2, 2], lower_better=False) == 100.0
    assert percentile_of(10, [1, 2, 3], lower_better=False) == 100.0
    assert percentile_of(0, [1, 2, 3], lower_better=False) == 0.0
    assert percentile_of(0, [1, 2, 3], lower_better=True) == 100.0
    assert percentile_of(1, [], lower_better=False) == 50.0
