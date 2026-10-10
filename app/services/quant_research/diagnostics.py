"""评分方法的上线诊断：只读、只返回**汇总统计**（不含任何个股代码 / 明细）。

用途：新方法版本（如 q7）上线后，对比它与上一版本在同一批股票上的结果——等级分布、各阶段的综合分、
新旧等级升降、排名相关、并列指标占比——判断有没有整体漂移、成长股是否被抬得过高。
纯函数，不碰数据库；读库在 repository.diagnostic_rows / get_distributions / panorama_rows / metric_values，接口在 api/v1/quant_research.py。
**临时工具**：方法稳定后可以删掉接口与本模块。

接口一览（均只读、只返回聚合、不含个股；删除时一并处理）：
- ``GET /quant-research/diagnostics``：新旧方法版本对比、等级分布、阶段占比与阶段判定敏感面（``stage_sensitivity``）。
- ``/diagnostics/scan``：从板块分布看指标覆盖 / 并列 / 极值。
- ``/diagnostics/whatif``：「综合分和谁比」三种口径的反事实（q10 的论证依据）。
- ``/diagnostics/netgap``：净利率与 EBIT 利润率的差距分布（一次性收益影响面）。
- ``/diagnostics/panorama``：维度相关 / 名义占比 vs 有效影响 / 板块偏差 / 指标体检 / 冗余指标 / 统一尺度反事实 / 各阶段画像。
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass

from app.services.quant_research.grading import GRADE_ORDER
from app.services.quant_research.metrics import DIMENSIONS, STABILITY_KEYS

MIN_GROUP = 10  # 分组少于这个只数不给均值 / 占比，避免汇总泄漏个股


@dataclass(frozen=True)
class DiagRow:
    symbol: str                      # 仅用于新旧配对，不会出现在输出里
    version: str | None
    grade: str | None
    score: float | None
    percentile: float | None
    capped: bool
    stage: str | None
    dim_grades: dict[str, str | None]
    rev_yoy_pct: float | None = None        # 阶段判定用的营收同比（%）
    rev_cagr3_pct: float | None = None      # 3 年复合（%）


@dataclass
class PanoRow:
    """全景统计用的一行：不含代码，只保留板块 / 阶段 / 综合 / 各维度 / 各指标的聚合所需字段。"""
    sector: str | None
    stage: str | None
    overall_score: float | None
    overall_pct: float | None
    dims: dict[str, tuple[float | None, int | None]]          # 维度键 → (分数, 在综合分里的占比 %)
    metrics: dict[str, tuple[str, float | None, str]]         # 指标键 → (状态, 板块内百分位, 所属维度键)


def _avg_ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    """秩相关（并列取平均位次）；少于 3 对或某一列没有变化返回 None。"""
    if len(a) != len(b) or len(a) < 3:
        return None
    ra, rb = _avg_ranks(a), _avg_ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    if da == 0 or db == 0:
        return None
    return round(sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True)) / (da * db), 3)


def _share(n: int, total: int) -> float | None:
    return round(n / total, 3) if total else None


def _rank_of(grade: str | None) -> int:
    """等级序号（A+ = 0 … F = 12，越小越好）；没有等级的行调用方已先过滤，这里兜底当最差。"""
    return GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER)


def summarize(rows: list[DiagRow]) -> dict:
    """一个方法版本 / 一天的结果汇总：等级分布、阶段分组、维度覆盖。"""
    graded = [r for r in rows if r.grade in GRADE_ORDER]
    out: dict = {
        "n": len(rows), "graded": len(graded),
        "versions": dict(Counter(r.version or "unknown" for r in rows)),
        "grade_share": {g: _share(sum(r.grade == g for r in graded), len(graded)) for g in GRADE_ORDER},
        "capped": sum(r.capped for r in graded),
        "stage_counts": dict(Counter(r.stage or "none" for r in rows)),
    }
    out["dimension_grade_share"] = {d: _band_share(rows, d) for d in DIMENSIONS}
    out["stage_sensitivity"] = stage_sensitivity(rows)
    by_stage: dict[str, dict] = {}
    for stage in sorted({r.stage or "none" for r in graded}):
        g = [r for r in graded if (r.stage or "none") == stage]
        if len(g) < MIN_GROUP:
            by_stage[stage] = {"n": len(g), "note": f"少于 {MIN_GROUP} 只，不给均值"}
            continue
        scores = [r.score for r in g if r.score is not None]
        pcts = [r.percentile for r in g if r.percentile is not None]
        by_stage[stage] = {
            "n": len(g),
            "score_mean": round(statistics.mean(scores), 1) if scores else None,
            "score_median": round(statistics.median(scores), 1) if scores else None,
            "percentile_mean": round(statistics.mean(pcts), 1) if pcts else None,
            "share_top_quartile": _share(sum(p >= 75 for p in pcts), len(pcts)),
            "share_b_minus_or_better": _share(sum(_rank_of(r.grade) <= GRADE_ORDER.index("B-") for r in g), len(g)),
            "share_f": _share(sum(r.grade == "F" for r in g), len(g)),
        }
    out["by_stage"] = by_stage
    return out


def _band_share(rows: list[DiagRow], dim: str) -> dict:
    """某维度等级按 A / B / C / D / F 档的占比（只算该维度有等级的）。"""
    have = [g for g in (r.dim_grades.get(dim) for r in rows) if g is not None and g in GRADE_ORDER]
    if not have:
        return {"covered": 0}
    out: dict = {"covered": len(have), "share_of_all": _share(len(have), len(rows))}
    for band in ("A", "B", "C", "D", "F"):
        out[band] = _share(sum(g.startswith(band) for g in have), len(have))
    return out


def compare(old: list[DiagRow], new: list[DiagRow]) -> dict:
    """同一批股票在两个方法版本下的差异（按代码配对，输出只含汇总）。"""
    o = {r.symbol: r for r in old if r.grade in GRADE_ORDER and r.score is not None}
    n = {r.symbol: r for r in new if r.grade in GRADE_ORDER and r.score is not None}
    common = sorted(set(o) & set(n))
    if len(common) < MIN_GROUP:
        return {"paired": len(common), "note": "配对不足，无法比较"}
    notches = [_rank_of(o[s].grade) - _rank_of(n[s].grade) for s in common]   # >0 = 升级（等级序号越小越好）
    dist: Counter[str] = Counter()
    for d in notches:
        dist["up_3_plus" if d >= 3 else "up_1_2" if d > 0 else "same" if d == 0 else "down_1_2" if d > -3 else "down_3_plus"] += 1
    old_scores = [float(o[s].score or 0.0) for s in common]
    new_scores = [float(n[s].score or 0.0) for s in common]
    out: dict = {
        "paired": len(common),
        "grade_change": {k: _share(v, len(common)) for k, v in dist.items()},
        "mean_notches_up": round(statistics.mean(notches), 2),
        "score_spearman": spearman(old_scores, new_scores),
        "mean_score_old": round(statistics.mean(old_scores), 1),
        "mean_score_new": round(statistics.mean(new_scores), 1),
        "by_stage_new": {},
    }
    # 无阶段公司再按有没有财务稳健等级拆开（判断排位下滑是不是缺这一维造成的）
    groups = {stage: [s for s in common if (n[s].stage or "none") == stage]
              for stage in sorted({n[s].stage or "none" for s in common})}
    none_all = groups.get("none", [])
    groups["none_with_stability"] = [s for s in none_all if n[s].dim_grades.get("stability")]
    groups["none_without_stability"] = [s for s in none_all if not n[s].dim_grades.get("stability")]
    for stage, ss in groups.items():
        if len(ss) < MIN_GROUP:
            continue
        po = [float(p) for p in (o[s].percentile for s in ss) if p is not None]
        pn = [float(p) for p in (n[s].percentile for s in ss) if p is not None]
        out["by_stage_new"][stage] = {
            "n": len(ss),
            "percentile_old": round(statistics.mean(po), 1) if po else None,
            "percentile_new": round(statistics.mean(pn), 1) if pn else None,
            "grade_up_share": _share(sum(_rank_of(o[s].grade) > _rank_of(n[s].grade) for s in ss), len(ss)),
            "grade_down_share": _share(sum(_rank_of(o[s].grade) < _rank_of(n[s].grade) for s in ss), len(ss)),
        }
    return out


def tie_stats(dists: dict[tuple[str, str], list[float]], keys: tuple[str, ...] | None = None) -> dict:
    """各指标「并列在极值」的公司占比（按板块取中位数）：并列严重的指标靠平均位次才不虚高。"""
    keys = keys or (*STABILITY_KEYS, "fcf_sbc_m")
    out: dict = {}
    for k in keys:
        shares = []
        for (_sector, metric), vals in dists.items():
            if metric != k or len(vals) < 20:
                continue
            top = max(Counter(vals).values())
            shares.append(top / len(vals))
        out[k] = {"sectors": len(shares), "median_largest_tie_share": round(statistics.median(shares), 3) if shares else None}
    return out


TIE_HEAVY_SHARE = 0.25     # 某板块某指标最大并列占比超过它：平均位次之外，该指标区分度也有限
FAT_TAIL_RATIO = 20.0      # 极值 / 第 99 百分位超过它：极少数异常值（单位 / 一次性项目 / 数据错）
THIN_COVERAGE = 0.6        # 指标有值的公司数 / 板块样本数低于它：数据源覆盖不足


# 合理性边界（拟用于 q10 的数据异常判定；这里只数有多少值越界，用数据说话后再决定要不要采用）
SANITY_BOUNDS: dict[str, float] = {"r3m": 10.0, "r6m": 10.0, "r9m": 10.0, "r12m": 20.0,
                                   "gross_m": 20.0, "ebit_m": 20.0, "ebitda_m": 20.0, "net_m": 20.0, "fcf_m": 20.0}


def _quantile(sorted_vals: list[float], q: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def scan_distributions(dists: dict[tuple[str, str], list[float]]) -> dict:
    """全景扫描：从板块分布（已落库的聚合数据）看每个指标有没有异常，**不读个股、不碰数据源**。

    每个指标汇总：覆盖率、分位、负值占比、最大并列占比、极值倍数，并给出标记（tie_heavy / fat_tail / thin_coverage /
    sparse_sectors）。输出只含指标键与统计量，不含个股。
    """
    sample = {sector: len(v) for (sector, key), v in dists.items() if key == "r3m"}
    total_sample = sum(sample.values())
    by_metric: dict[str, dict[str, list[float]]] = {}
    for (sector, key), vals in dists.items():
        if key.startswith("_") or sector.startswith("_"):      # 综合分分布不是指标
            continue
        by_metric.setdefault(key, {})[sector] = vals
    out: dict = {"sample_total": total_sample, "metrics": {}, "flagged": {}}
    for key, per_sector in sorted(by_metric.items()):
        pooled = sorted(v for vals in per_sector.values() for v in vals)
        if not pooled:
            continue
        sectors_with = {s: vals for s, vals in per_sector.items() if vals}
        tie = [max(Counter(vals).values()) / len(vals) for vals in sectors_with.values() if len(vals) >= 20]
        p99, p95 = _quantile(pooled, 0.99), _quantile(pooled, 0.95)
        flags = []
        coverage = len(pooled) / total_sample if total_sample else None
        if coverage is not None and coverage < THIN_COVERAGE:
            flags.append("thin_coverage")
        if tie and statistics.median(tie) > TIE_HEAVY_SHARE:
            flags.append("tie_heavy")
        if p99 > 0 and pooled[-1] / p99 > FAT_TAIL_RATIO or p99 < 0 and pooled[0] / p99 > FAT_TAIL_RATIO:
            flags.append("fat_tail")
        if len(sectors_with) < len(sample):
            flags.append("sparse_sectors")
        out["metrics"][key] = {
            "n": len(pooled), "coverage": round(coverage, 3) if coverage is not None else None,
            "sectors": len(sectors_with),
            "p1": round(_quantile(pooled, 0.01), 4), "p50": round(_quantile(pooled, 0.5), 4),
            "p95": round(p95, 4), "p99": round(p99, 4), "max": round(pooled[-1], 4),
            "negative_share": round(sum(v < 0 for v in pooled) / len(pooled), 3),
            "median_largest_tie_share": round(statistics.median(tie), 3) if tie else None,
            "flags": flags,
        }
        if key in SANITY_BOUNDS:
            bound = SANITY_BOUNDS[key]
            out["metrics"][key]["beyond_sanity_bound"] = {"bound": bound, "count": sum(abs(v) > bound for v in pooled)}
        if flags:
            out["flagged"][key] = flags
    return out


COHORT_STAGES_Q10 = ("growth", "mature", "none")   # 方案：只有样本大且本身不是弱势的阶段做同阶段排位
COHORT_MIN_SAMPLE = 30                               # 与 scoring.COHORT_MIN 一致


def whatif_cohort(rows: list[DiagRow]) -> dict:
    """反事实：用已存的综合分，比较三种「综合分和谁比」的口径下各阶段的等级分布（不含防抖与一票否决，只看排位口径的差异）。

    universe = 全体（q7）；all_stages = 每个样本 ≥30 的阶段都和同阶段比（q8 / q9 现状）；
    selective = 只有 growth / mature / none 和同阶段比，其余阶段仍和全体比（q10 方案）。
    只读已落库的结果，输出为各阶段汇总，分组少于 MIN_GROUP 只不给数字。
    """
    from app.services.quant_research.grading import grade_for, percentile_of

    scored = [r for r in rows if r.score is not None]
    if len(scored) < MIN_GROUP:
        return {"note": "样本不足"}
    allv = sorted(float(r.score) for r in scored)                                     # type: ignore[arg-type]
    by_stage: dict[str, list[float]] = {}
    for r in scored:
        by_stage.setdefault(r.stage or "none", []).append(float(r.score))             # type: ignore[arg-type]
    cohort = {k: sorted(v) for k, v in by_stage.items() if len(v) >= COHORT_MIN_SAMPLE}

    def pct(r: DiagRow, scheme: str) -> float:
        s = float(r.score)                                                             # type: ignore[arg-type]
        stage = r.stage or "none"
        use = stage in cohort and (scheme == "all_stages" or (scheme == "selective" and stage in COHORT_STAGES_Q10))
        return percentile_of(s, cohort[stage] if use else allv, lower_better=False)

    graded = [r for r in scored if r.grade in GRADE_ORDER]       # 有综合等级的（分析师够）
    b_minus = GRADE_ORDER.index("B-")
    out: dict = {"scored": len(scored), "graded": len(graded), "cohort_stages": sorted(cohort), "by_stage": {}}
    for stage in sorted({r.stage or "none" for r in graded}):
        g = [r for r in graded if (r.stage or "none") == stage]
        if len(g) < MIN_GROUP:
            continue
        entry: dict = {"n": len(g), "cohort_size": len(by_stage.get(stage, []))}
        for scheme in ("universe", "all_stages", "selective"):
            ps = [pct(r, scheme) for r in g]
            grades = [GRADE_ORDER.index(grade_for(p)) for p in ps]
            entry[scheme] = {
                "percentile_mean": round(statistics.mean(ps), 1),
                "share_b_minus_or_better": _share(sum(x <= b_minus for x in grades), len(g)),
                "share_f": _share(sum(x == len(GRADE_ORDER) - 1 for x in grades), len(g)),
            }
        out["by_stage"][stage] = entry
    total: dict = {}
    for scheme in ("universe", "all_stages", "selective"):
        grades = [GRADE_ORDER.index(grade_for(pct(r, scheme))) for r in graded]
        total[scheme] = {"share_b_minus_or_better": _share(sum(x <= b_minus for x in grades), len(graded)),
                         "share_f": _share(sum(x == len(GRADE_ORDER) - 1 for x in grades), len(graded))}
    out["overall"] = total
    return out


def stage_sensitivity(rows: list[DiagRow]) -> dict:
    """阶段判定的敏感面（只读已存的营收同比 / 3 年复合，输出为占比）：

    ramp_zone = 同比在 10%~20%（成长门槛 15% 两侧，标签与权重最容易不一致）；
    extreme_yoy = 同比 > 100% 或 < -50%（多为分拆 / 并购 / 重述造成的序列断点，WDC 一类）；
    cagr_missing = 没有 3 年复合（上市不足 3 年或历史缺失）；no_yoy = 同比缺失（无法分阶段）。
    """
    staged = [r for r in rows if r.stage is not None]
    if len(staged) < MIN_GROUP:
        return {"note": "样本不足"}
    yoy = [r.rev_yoy_pct for r in staged if r.rev_yoy_pct is not None]
    return {
        "staged": len(staged),
        "no_yoy": _share(len(staged) - len(yoy), len(staged)),
        "ramp_zone_10_20": _share(sum(10.0 <= v <= 20.0 for v in yoy), len(staged)),
        "extreme_yoy": _share(sum(v > 100.0 or v < -50.0 for v in yoy), len(staged)),
        "cagr_missing": _share(sum(r.rev_cagr3_pct is None for r in staged), len(staged)),
        "yoy_percentiles": {f"p{q}": round(sorted(yoy)[min(len(yoy) - 1, int(q / 100 * len(yoy)))], 1) for q in (5, 25, 50, 75, 95)} if yoy else {},
    }


def net_margin_gap(values: list[dict[str, float]]) -> dict:
    """净利率 vs 经营（EBIT）利润率：净利率明显高于经营利润率，多是处置收益 / 公允价值变动 / 税收收益等一次性项目（WDC 一类）。

    只看同时有两项的公司；输出各档占比，不含个股。gap = 净利率 − EBIT 利润率（百分点）。
    """
    pairs = [(v["net_m"], v["ebit_m"]) for v in values if "net_m" in v and "ebit_m" in v]
    if len(pairs) < MIN_GROUP:
        return {"note": "样本不足"}
    gaps = [(n - e) * 100 for n, e in pairs]
    total = len(gaps)
    return {
        "paired": total,
        "gap_gt_5pt": _share(sum(g > 5 for g in gaps), total),
        "gap_gt_10pt": _share(sum(g > 10 for g in gaps), total),
        "gap_gt_20pt": _share(sum(g > 20 for g in gaps), total),
        "net_margin_gt_50pct": _share(sum(n > 0.5 for n, _ in pairs), total),
        "gap_percentiles_pt": {f"p{q}": round(sorted(gaps)[min(total - 1, int(q / 100 * total))], 1) for q in (50, 90, 95, 99)},
    }


PANO_MIN_SECTOR = 10      # 板块少于这个只数不给均值
PANO_SECTOR_BIAS_PT = 8.0       # 板块平均综合排位偏离 50 超过它：板块偏差
PANO_METRIC_BIAS_PT = 8.0       # 指标平均百分位偏离 50 超过它：该指标的百分位分布不均
PANO_REDUNDANT_CORR = 0.9       # 同维度内两个指标百分位的秩相关超过它：信息重复


def _pair_corr(a: dict[int, float], b: dict[int, float]) -> float | None:
    keys = sorted(set(a) & set(b))
    return spearman([a[k] for k in keys], [b[k] for k in keys]) if len(keys) >= 30 else None


def _ok_pcts(rows: list[PanoRow], key: str) -> dict[int, float]:
    out: dict[int, float] = {}
    for j, r in enumerate(rows):
        m = r.metrics.get(key)
        if m is not None and m[0] == "ok" and m[1] is not None:
            out[j] = m[1]
    return out


def panorama(rows: list[PanoRow]) -> dict:
    """维度与指标的统计体检（只读已存结果、输出为聚合）：

    1. dim_corr：各维度分数的两两秩相关（太高 = 信息重复，接近 0 = 互相独立）；
    2. dim_influence：每个维度「名义占比」vs「对综合分的有效影响」（权重 × 分数与综合分的协方差占比），看有没有维度名不副实；
    3. sector_bias：各板块平均综合排位（综合分是全体排位，板块结构性偏高 / 偏低要留意）；
    4. metric_quality：每个指标的状态占比、平均百分位、两端占比，标出覆盖不足 / 百分位分布不均；
    5. metric_redundancy：同维度内百分位高度相关的指标对。
    """
    scored = [r for r in rows if r.overall_score is not None]
    if len(scored) < MIN_GROUP:
        return {"note": "样本不足"}
    dim_keys = sorted({k for r in scored for k in r.dims})
    # 1) 维度间相关
    dim_vals: dict[str, dict[int, float]] = {d: {} for d in dim_keys}
    for i, r in enumerate(scored):
        for d, (sc, _w) in r.dims.items():
            if sc is not None:
                dim_vals[d][i] = sc
    dim_corr = {f"{a}~{b}": c for i, a in enumerate(dim_keys) for b in dim_keys[i + 1:]
                if (c := _pair_corr(dim_vals[a], dim_vals[b])) is not None}
    # 2) 名义占比 vs 有效影响（协方差占比，和为 1）
    comp = [float(r.overall_score) for r in scored]                                    # type: ignore[arg-type]
    mc = statistics.mean(comp)
    var_c = statistics.pvariance(comp)
    influence: dict[str, dict] = {}
    for d in dim_keys:
        contrib = [((r.dims[d][0] or 0.0) * (r.dims[d][1] or 0) / 100.0) if d in r.dims else 0.0 for r in scored]
        mx = statistics.mean(contrib)
        cov = statistics.mean((x - mx) * (c - mc) for x, c in zip(contrib, comp, strict=True))
        weights = [float(w) for r in scored if d in r.dims and (w := r.dims[d][1]) is not None]
        influence[d] = {"nominal_weight_pct": round(statistics.mean(weights), 1) if weights else None,
                        "effective_influence_pct": round(cov / var_c * 100, 1) if var_c else None,
                        "covered_share": _share(len(weights), len(scored))}
    # 3) 板块偏差
    by_sector: dict[str, list[PanoRow]] = {}
    for r in scored:
        by_sector.setdefault(r.sector or "unknown", []).append(r)
    sector_bias = {}
    for sec, rs in sorted(by_sector.items()):
        pcts = [r.overall_pct for r in rs if r.overall_pct is not None]
        if len(rs) < PANO_MIN_SECTOR or not pcts:
            continue
        sector_bias[sec] = {"n": len(rs), "mean_pct": round(statistics.mean(pcts), 1),
                            "share_top_quartile": _share(sum(p >= 75 for p in pcts), len(pcts)),
                            "flag": abs(statistics.mean(pcts) - 50) > PANO_SECTOR_BIAS_PT}
    # 4) 指标体检
    metric_keys = sorted({k for r in rows for k in r.metrics})
    quality: dict[str, dict] = {}
    for k in metric_keys:
        have = [r.metrics[k] for r in rows if k in r.metrics]
        total = len(have)
        status = Counter(s for s, _, _ in have)
        pcts = [p for s, p, _ in have if s == "ok" and p is not None]
        ok_share = _share(status.get("ok", 0), total)
        flags = []
        if ok_share is not None and ok_share < 0.6:
            flags.append("low_ok_share")
        if pcts and abs(statistics.mean(pcts) - 50) > PANO_METRIC_BIAS_PT:
            flags.append("skewed_percentile")
        quality[k] = {"n": total, "ok": ok_share,
                      "not_meaningful": _share(status.get("not_meaningful", 0), total),
                      "not_applicable": _share(status.get("not_applicable", 0), total),
                      "missing": _share(status.get("missing", 0), total),
                      "mean_pct": round(statistics.mean(pcts), 1) if pcts else None,
                      "at_bottom_5": _share(sum(p <= 5 for p in pcts), len(pcts)) if pcts else None,
                      "at_top_95": _share(sum(p >= 95 for p in pcts), len(pcts)) if pcts else None,
                      "flags": flags}
    # 5) 同维度指标冗余
    by_dim: dict[str, list[str]] = {}
    for r in rows:
        for k, (_s, _p, d) in r.metrics.items():
            by_dim.setdefault(d, [])
            if k not in by_dim[d]:
                by_dim[d].append(k)
    redundant = []
    for d, ks in by_dim.items():
        for i, a in enumerate(sorted(ks)):
            for b in sorted(ks)[i + 1:]:
                va = _ok_pcts(rows, a)
                vb = _ok_pcts(rows, b)
                c = _pair_corr(va, vb)
                if c is not None and c >= PANO_REDUNDANT_CORR:
                    redundant.append({"dimension": d, "pair": f"{a}~{b}", "corr": c})
    return {
        "n": len(rows), "scored": len(scored), "dim_corr": dim_corr, "dim_influence": influence,
        "sector_bias": sector_bias, "metric_quality": quality,
        "flagged_metrics": {k: v["flags"] for k, v in quality.items() if v["flags"]},
        "redundant_metric_pairs": sorted(redundant, key=lambda x: -x["corr"])[:15],
        "rebalance_whatif": rebalance_whatif(scored),
        "by_stage": by_stage_profile(rows),
    }


def _influence(contribs: dict[str, list[float]], comp: list[float]) -> dict[str, float]:
    """各维度对综合分的有效影响（贡献与综合分的协方差 ÷ 综合分方差，%）。"""
    mc = statistics.mean(comp)
    var_c = statistics.pvariance(comp)
    out: dict[str, float] = {}
    for d, xs in contribs.items():
        mx = statistics.mean(xs)
        out[d] = round(statistics.mean((x - mx) * (c - mc) for x, c in zip(xs, comp, strict=True)) / var_c * 100, 1) if var_c else 0.0
    return out


def rebalance_whatif(scored: list[PanoRow]) -> dict:
    """反事实：把每个维度分数先换成它在全体里的百分位（同一把尺度），再按同样的实际权重合成。

    目的：权重表写的占比是否真的等于「对排名的影响」。维度分数分散度不同（取平均的指标个数、相关性不同），
    名义占比会和有效影响脱节；这里看统一尺度后：综合排名变多少（秩相关）、有效影响是否贴近名义占比、等级变化的分布。
    只读已存的维度分数与权重，不含阶段同阶段排位 / 一票否决 / 防抖（只比较排位口径差异）。
    """
    from app.services.quant_research.grading import grade_for, percentile_of

    dims = sorted({d for r in scored for d in r.dims})
    dist = {d: sorted(r.dims[d][0] for r in scored if d in r.dims and r.dims[d][0] is not None) for d in dims}   # type: ignore[misc]
    cur: list[float] = []
    alt: list[float] = []
    contrib_cur: dict[str, list[float]] = {d: [] for d in dims}
    contrib_alt: dict[str, list[float]] = {d: [] for d in dims}
    for r in scored:
        use = [(d, sc, w) for d, (sc, w) in r.dims.items() if sc is not None and w]
        tw = sum(w for _, _, w in use)
        if not use or tw <= 0:
            continue
        a = {d: percentile_of(sc, dist[d], lower_better=False) for d, sc, _ in use}
        cur.append(float(r.overall_score))                                           # type: ignore[arg-type]
        alt.append(sum(a[d] * w for d, _, w in use) / tw)
        have = {d: (sc, w) for d, sc, w in use}
        for d in dims:
            contrib_cur[d].append(have[d][0] * have[d][1] / tw if d in have else 0.0)
            contrib_alt[d].append(a[d] * have[d][1] / tw if d in have else 0.0)
    if len(cur) < MIN_GROUP:
        return {"note": "样本不足"}
    sc_c, sc_a = sorted(cur), sorted(alt)
    notch = [GRADE_ORDER.index(grade_for(percentile_of(c, sc_c, lower_better=False)))
             - GRADE_ORDER.index(grade_for(percentile_of(a, sc_a, lower_better=False))) for c, a in zip(cur, alt, strict=True)]
    top_cur = {i for i, c in enumerate(cur) if percentile_of(c, sc_c, lower_better=False) >= 75}
    top_alt = {i for i, a in enumerate(alt) if percentile_of(a, sc_a, lower_better=False) >= 75}
    return {
        "n": len(cur),
        "rank_corr_current_vs_rescaled": spearman(cur, alt),
        "influence_current_pct": _influence(contrib_cur, cur),
        "influence_rescaled_pct": _influence(contrib_alt, alt),
        "grade_change_share": {
            "same": _share(sum(n == 0 for n in notch), len(notch)),
            "within_1_notch": _share(sum(abs(n) <= 1 for n in notch), len(notch)),
            "ge_3_notches": _share(sum(abs(n) >= 3 for n in notch), len(notch)),
        },
        "top_quartile_overlap": _share(len(top_cur & top_alt), len(top_cur)),
    }


def by_stage_profile(rows: list[PanoRow]) -> dict:
    """各阶段的维度平均分、弱分占比，以及盈利能力里各指标的平均百分位（看某个阶段在某类指标上是否系统性偏低）。

    只读已存数据；分组少于 MIN_GROUP 只不给数字。弱分 = 维度分 < 30，强分 = ≥ 70。
    """
    out: dict = {}
    for stage in sorted({r.stage or "none" for r in rows}):
        g = [r for r in rows if (r.stage or "none") == stage]
        if len(g) < MIN_GROUP:
            continue
        dims: dict[str, dict] = {}
        for d in sorted({k for r in g for k in r.dims}):
            xs = [sc for r in g if d in r.dims and (sc := r.dims[d][0]) is not None]
            if len(xs) >= MIN_GROUP:
                dims[d] = {"n": len(xs), "mean": round(statistics.mean(xs), 1),
                           "share_weak_lt30": _share(sum(x < 30 for x in xs), len(xs)),
                           "share_strong_ge70": _share(sum(x >= 70 for x in xs), len(xs))}
        prof: dict[str, float] = {}
        for k in sorted({k for r in g for k, (_s, _p, dim) in r.metrics.items() if dim == "profitability"}):
            ps = [p for r in g if k in r.metrics and r.metrics[k][0] == "ok" and (p := r.metrics[k][1]) is not None]
            if len(ps) >= MIN_GROUP:
                prof[k] = round(statistics.mean(ps), 1)
        out[stage] = {"n": len(g), "dimension_scores": dims, "profitability_metric_mean_pct": prof}
    return out
