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


def test_scan_distributions_flags_ties_fat_tails_and_thin_coverage():
    from app.services.quant_research.diagnostics import scan_distributions

    normal = [float(i) for i in range(1, 101)]
    dists = {
        ("tech", "r3m"): normal, ("fin", "r3m"): normal,                      # 板块样本 100 + 100
        ("tech", "pe_ttm"): normal, ("fin", "pe_ttm"): normal,                # 正常
        ("tech", "interest_cov"): [100.0] * 60 + normal[:40], ("fin", "interest_cov"): [100.0] * 60 + normal[:40],  # 并列严重
        ("tech", "roe"): normal[:-1] + [100000.0], ("fin", "roe"): normal,    # 极值离谱
        ("tech", "pb"): normal[:30],                                          # 覆盖不足 + 只有一个板块有值
        ("_all", "_overall"): normal,                                         # 综合分分布不是指标
    }
    r = scan_distributions(dists)
    assert r["sample_total"] == 200 and "_overall" not in r["metrics"]
    assert r["metrics"]["pe_ttm"]["flags"] == []
    assert "tie_heavy" in r["flagged"]["interest_cov"]
    assert "fat_tail" in r["flagged"]["roe"]
    assert {"thin_coverage", "sparse_sectors"} <= set(r["flagged"]["pb"])
    assert all("symbol" not in str(v) for v in r["metrics"].values())


def test_whatif_cohort_selective_keeps_weak_stages_on_the_universe_scale():
    """selective：成长 / 成熟只和同阶段比；调整期这类弱势阶段仍和全体比，所以它的弱势不会被抹平。"""
    from app.services.quant_research.diagnostics import whatif_cohort

    rows = [DiagRow(f"m{i}", "q9", "B", 50.0 + i * 0.1, None, False, "mature", {}) for i in range(60)]
    rows += [DiagRow(f"w{i}", "q9", "C", 20.0 + i * 0.1, None, False, "shakeout", {}) for i in range(40)]   # 整体明显更弱
    r = whatif_cohort(rows)
    sk = r["by_stage"]["shakeout"]
    assert sk["all_stages"]["percentile_mean"] > 45          # 和同阶段比：弱势被抹平，平均排位回到 50 上下
    assert sk["selective"]["percentile_mean"] < 25           # 仍和全体比：保持真实的弱
    assert abs(sk["selective"]["percentile_mean"] - sk["universe"]["percentile_mean"]) < 1e-6
    mt = r["by_stage"]["mature"]
    assert mt["selective"] == mt["all_stages"]               # 成熟期两种口径一致


def test_stage_sensitivity_counts_ramp_extreme_and_missing():
    from app.services.quant_research.diagnostics import stage_sensitivity

    def row(i, yoy, cagr):
        return DiagRow(f"s{i}", "q10", "B", 50.0, 50.0, False, "mature", {}, yoy, cagr)

    rows = ([row(i, 5.0, 3.0) for i in range(6)] + [row(10 + i, 15.0, 8.0) for i in range(2)]
            + [row(20, 250.0, None), row(21, -80.0, 4.0), row(22, None, None)])
    r = stage_sensitivity(rows)
    assert r["staged"] == 11
    assert r["ramp_zone_10_20"] == round(2 / 11, 3) and r["extreme_yoy"] == round(2 / 11, 3)
    assert r["cagr_missing"] == round(2 / 11, 3) and r["no_yoy"] == round(1 / 11, 3)


def test_net_margin_gap_buckets():
    from app.services.quant_research.diagnostics import net_margin_gap

    vals = [{"net_m": 0.10, "ebit_m": 0.12}] * 8 + [{"net_m": 0.73, "ebit_m": 0.35}, {"net_m": 0.20, "ebit_m": 0.12}, {"net_m": 0.4}]
    r = net_margin_gap(vals)
    assert r["paired"] == 10 and r["gap_gt_5pt"] == 0.2 and r["gap_gt_10pt"] == 0.1 and r["gap_gt_20pt"] == 0.1
    assert r["net_margin_gt_50pct"] == 0.1


def test_panorama_flags_redundancy_sector_bias_and_low_coverage():
    import random

    from app.services.quant_research.diagnostics import PanoRow, panorama

    rnd = random.Random(7)
    rows = []
    for i in range(120):
        base = rnd.uniform(0, 100)
        sec = "utilities" if i < 40 else "tech"
        pct_a = base
        dims = {"valuation": (base, 40), "growth": (rnd.uniform(0, 100), 60)}
        metrics = {
            "pe": ("ok", pct_a, "valuation"), "pe_fwd": ("ok", min(100.0, pct_a + 1), "valuation"),    # 与 pe 几乎同序
            "rare": ("ok" if i % 5 == 0 else "missing", pct_a, "growth"),                              # 覆盖不足
        }
        score = (35 if sec == "utilities" else 62) + rnd.uniform(-5, 5)
        rows.append(PanoRow(sec, "mature", score, score, dims, metrics))
    r = panorama(rows)
    assert r["sector_bias"]["utilities"]["flag"] is True and r["sector_bias"]["tech"]["flag"] is True
    assert "low_ok_share" in r["flagged_metrics"]["rare"]
    assert any(p["pair"] == "pe~pe_fwd" for p in r["redundant_metric_pairs"])
    assert set(r["dim_influence"]) == {"valuation", "growth"} and "growth~valuation" in r["dim_corr"]
    assert "symbol" not in str(r)


def test_rebalance_whatif_equalizes_dispersion():
    """维度 A 分散度大、B 分散度小而名义占比相同：统一尺度后 B 的有效影响应明显上升、A 下降。"""
    import random

    from app.services.quant_research.diagnostics import PanoRow, rebalance_whatif

    rnd = random.Random(3)
    rows = []
    for _ in range(400):
        a = rnd.uniform(0, 100)
        b = 50 + rnd.uniform(-5, 5)                       # 几乎不分散
        rows.append(PanoRow("s", "mature", (a + b) / 2, None, {"a": (a, 50), "b": (b, 50)}, {}))
    r = rebalance_whatif(rows)
    assert r["influence_current_pct"]["a"] > 90 and r["influence_current_pct"]["b"] < 10
    assert r["influence_rescaled_pct"]["b"] > r["influence_current_pct"]["b"] + 30
    assert 0 < r["rank_corr_current_vs_rescaled"] < 1 and "symbol" not in str(r)


def test_by_stage_profile_shows_stage_specific_weakness():
    from app.services.quant_research.diagnostics import PanoRow, by_stage_profile

    def row(stage, prof, gm, gaap):
        return PanoRow("s", stage, 50.0, 50.0, {"profitability": (prof, 20)},
                       {"gross_m": ("ok", gm, "profitability"), "roic": ("ok", gaap, "profitability")})

    rows = [row("growth", 25.0, 80.0, 5.0) for _ in range(12)] + [row("mature", 60.0, 50.0, 60.0) for _ in range(12)] + [row("intro", 10.0, 50.0, 5.0)]
    r = by_stage_profile(rows)
    g = r["growth"]
    assert g["dimension_scores"]["profitability"]["mean"] == 25.0 and g["dimension_scores"]["profitability"]["share_weak_lt30"] == 1.0
    assert g["profitability_metric_mean_pct"] == {"gross_m": 80.0, "roic": 5.0}      # 毛利率高、GAAP 回报极低
    assert "intro" not in r                                                         # 样本不足不给数字


def test_sbc_adjust_whatif_lifts_stock_comp_heavy_and_leaves_light_alone():
    from app.services.quant_research.diagnostics import SbcRow, sbc_adjust_whatif

    rows = []
    # 重股权激励组：经营利润率为负，加回股权激励后接近盈亏平衡（排位上升）
    for i in range(20):
        rows.append(SbcRow("tech", "growth", 50.0 + i * 0.2, 10.0, 40, -0.05 + i * 0.002, 0.10, 0.0,
                           ("ebit_m", "gross_m", "roic")))
    # 无股权激励组：加回量为 0，排位不变
    for i in range(20):
        rows.append(SbcRow("tech", "growth", 51.0 + i * 0.2, 60.0, 40, 0.05 + i * 0.005, 0.05, 0.05,
                           ("ebit_m", "gross_m", "roic")))
    out = sbc_adjust_whatif(rows)
    heavy = out["by_sbc_share"]["ge_10pct"]
    light = out["by_sbc_share"]["lt_3pct"]
    assert heavy["n"] == 20 and light["n"] == 20
    assert heavy["mean_pct_change"] > light["mean_pct_change"]
    assert out["overall"]["rank_corr"] is not None
    assert "symbol" not in str(out)


def test_sbc_adjust_whatif_small_sample():
    from app.services.quant_research.diagnostics import sbc_adjust_whatif

    assert sbc_adjust_whatif([])["note"] == "样本不足"


def test_nongaap_summary_buckets_and_suppression():
    from app.services.quant_research.diagnostics import NgRow, nongaap_summary

    rows = []
    for i in range(12):   # 亏损但非 GAAP 盈利（成长）
        rows.append(NgRow("tech", "growth", -1.0 - i * 0.01, 1.5, 8))
    for i in range(14):   # 两口径基本一致（成熟）
        rows.append(NgRow("health", "mature", 5.0 + i * 0.1, 5.1 + i * 0.1, 8))
    for _ in range(4):    # 没有实际 EPS
        rows.append(NgRow("health", "mature", 2.0, None, 0))
    out = nongaap_summary(rows)
    assert out["n"] == 30
    assert out["coverage_4q"] == round(26 / 30, 3)
    assert out["gaap_loss_nongaap_profit"] == round(12 / 26, 3)
    assert out["gap_gt_100pct"] == round(12 / 26, 3)
    assert out["by_stage"]["growth"]["gaap_loss_nongaap_profit"] == 1.0
    assert "symbol" not in str(out)
    assert nongaap_summary(rows[:5])["note"] == "样本不足"
