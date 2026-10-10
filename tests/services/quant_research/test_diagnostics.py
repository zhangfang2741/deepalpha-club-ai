"""上线诊断：纯函数统计 + 汇总里不能带出任何个股代码。"""

import json

from app.services.quant_research.diagnostics import MIN_GROUP, DiagRow, compare, spearman, summarize, tie_stats
from app.services.quant_research.grading import GRADE_ORDER


def _row(sym, grade, score, pct, stage="growth", version="q7", capped=False, **dims):
    return DiagRow(sym, version, grade, score, pct, capped, stage, dims)


def _rows(prefix, n, stage="growth", version="q7", grade="B", score=60.0, pct=70.0):
    return [_row(f"{prefix}{i}", grade, score + i * 0.1, pct, stage, version) for i in range(n)]


def test_spearman_basic_and_degenerate():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None       # 一列没有变化
    assert spearman([1, 2], [1, 2]) is None                    # 太少


def test_summarize_groups_and_small_group_suppressed():
    rows = _rows("a", MIN_GROUP + 2, "growth") + _rows("b", 3, "mature", grade="D", score=40.0, pct=30.0)
    s = summarize(rows)
    assert s["n"] == MIN_GROUP + 5 and s["versions"] == {"q7": MIN_GROUP + 5}
    assert s["by_stage"]["growth"]["score_mean"] is not None and s["by_stage"]["growth"]["share_top_quartile"] == 0.0
    assert "score_mean" not in s["by_stage"]["mature"]          # 少于 MIN_GROUP 只：不给均值，防止泄漏个股
    assert set(s["grade_share"]) == set(GRADE_ORDER)


def test_compare_counts_notches_and_stage_shift():
    old = [_row(f"s{i}", "C", 50.0 + i, 50.0, "growth", "q6") for i in range(12)]
    new = [_row(f"s{i}", "C+" if i % 2 == 0 else "C", 55.0 + i, 62.0, "growth", "q7") for i in range(12)]
    c = compare(old, new)
    assert c["paired"] == 12
    assert c["grade_change"]["up_1_2"] == 0.5 and c["grade_change"]["same"] == 0.5
    assert c["score_spearman"] == 1.0
    g = c["by_stage_new"]["growth"]
    assert g["percentile_old"] == 50.0 and g["percentile_new"] == 62.0 and g["grade_up_share"] == 0.5


def test_compare_needs_enough_pairs():
    assert "note" in compare(_rows("a", 3, version="q6"), _rows("a", 3))


def test_summary_never_contains_symbols():
    rows = _rows("SECRETSYM", 15) + _rows("OTHERSYM", 12, "mature")
    out = json.dumps({"s": summarize(rows), "c": compare(rows, rows)}, ensure_ascii=False)
    assert "SECRETSYM" not in out and "OTHERSYM" not in out


def test_tie_stats_median_largest_tie_share():
    dists = {("it", "runway_years"): sorted([float(i) for i in range(3)] + [10.0] * 97),
             ("fin", "runway_years"): sorted([10.0] * 50 + [float(i) for i in range(50)]),
             ("tiny", "runway_years"): [1.0, 2.0],                  # 样本不足 20：不统计
             ("it", "cfo_ni"): [float(i) for i in range(100)]}
    t = tie_stats(dists, ("runway_years", "cfo_ni"))
    assert t["runway_years"] == {"sectors": 2, "median_largest_tie_share": 0.74}   # (97% + 51%) 的中位数
    assert t["cfo_ni"]["median_largest_tie_share"] == 0.01
