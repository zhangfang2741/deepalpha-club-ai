"""评分方法的上线诊断：只读、只返回**汇总统计**（不含任何个股代码 / 明细）。

用途：新方法版本（如 q7）上线后，对比它与上一版本在同一批股票上的结果——等级分布、各阶段的综合分、
新旧等级升降、排名相关、并列指标占比——判断有没有整体漂移、成长股是否被抬得过高。
纯函数，不碰数据库；读库在 repository.diagnostic_rows / get_distributions，接口在 api/v1/quant_research.py。
**临时工具**：方法稳定后可以删掉接口与本模块。
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
        if flags:
            out["flagged"][key] = flags
    return out
