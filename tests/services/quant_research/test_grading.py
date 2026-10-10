"""等级分档、板块百分位与防抖动。"""

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


def test_percentile_ties_use_mean_rank():
    """并列取平均排名：70% 的公司并列在极值时，它们不能都拿 100 分位（界面写的是「高于 x% 的公司」）。"""
    dist = sorted([0.0] * 70 + [float(i) for i in range(1, 31)])      # 70 家净现金（净负债比 = 0）+ 30 家有负债
    assert percentile_of(0.0, dist, lower_better=True) == 65.5        # 越低越好：(30 比它差 + 70 家并列的平均位次 35.5) ÷ 100
    assert percentile_of(30.0, dist, lower_better=True) == 1.0        # 最差的那家仍是 1
    cap = sorted([float(i) for i in range(1, 4)] + [10.0] * 97)       # 97% 并列在上限（不烧钱）
    assert percentile_of(10.0, cap, lower_better=False) == 52.0       # 越高越好：并列 97 家占据位次 4~100，平均 52
    assert percentile_of(3.0, cap, lower_better=False) == 3.0         # 唯一值的结果与旧算法一致
    assert percentile_of(2, [2, 2, 2, 2], lower_better=False) == 62.5  # 全并列 = 正中间，不是 100
    assert percentile_of(2, [2, 2, 2, 2], lower_better=True) == 62.5


def test_percentile_unique_values_unchanged():
    values = [float(i) for i in range(1, 101)]
    for v in (1, 17, 50, 100):
        assert percentile_of(v, values, lower_better=False) == v
        assert percentile_of(v, values, lower_better=True) == 101 - v


def test_percentile_out_of_sample():
    assert percentile_of(10, [1, 2, 3], lower_better=False) == 100.0
    assert percentile_of(0, [1, 2, 3], lower_better=False) == 0.0
    assert percentile_of(0, [1, 2, 3], lower_better=True) == 100.0
    assert percentile_of(1, [], lower_better=False) == 50.0
