"""量化研究文案：措辞模板与禁用词守护。"""

import itertools

import pytest

from app.services.quant_research.copy import (
    DISCLAIMER,
    STAGE_NOTES,
    contains_forbidden,
    dimension_formula,
    dimension_status_note,
    dims_used_note,
    fmt_metric_value,
    fmt_money,
    key_fact_text,
    metric_expression,
    metric_status_note,
    overall_note,
    overall_text,
    position_text,
    stage_note,
)
from app.services.quant_research.metrics import METRICS, MetricValue, compute_metrics
from app.services.quant_research.scoring import DimensionScore, OverallScore, ScoredMetric, score_metric
from tests.services.quant_research.fixtures import load_inputs

DIST = [float(i) for i in range(1, 101)]
LANGS = ["zh", "en"]


def _all_texts():
    texts = list(DISCLAIMER.values())
    for sym, lang in itertools.product(["NVDA", "JPM", "O", "XOM"], LANGS):
        for key, mv in compute_metrics(load_inputs(sym)).items():
            dist = [v / 10 for v in DIST] if METRICS[key].unit == "pct" else DIST
            sm = score_metric(key, mv, dist, None)
            texts += [key_fact_text(sm, lang), metric_expression(key, mv, lang),
                      position_text(sm, lang) or "", metric_status_note(sm, lang) or ""]
    for lang in LANGS:
        for st in ("not_meaningful", "not_applicable", "missing", "insufficient_sample"):
            for key in ("pe_ttm", "pb", "roic", "ev_ebitda_ttm", "rev_fwd"):
                texts.append(metric_status_note(ScoredMetric(key, MetricValue(None, st), st, None, None, 0), lang) or "")
        for k in STAGE_NOTES:
            texts += [stage_note(k, True, lang), stage_note(k, False, lang)]
        texts += [overall_note(OverallScore(80, 90, "C+", 5, True, "valuation"), lang) or "",
                  overall_note(OverallScore(80, 90, None, 5, extra={"reason": "few_analysts"}), lang) or "",
                  overall_text(OverallScore(78.4, 92.1, "A", 5), lang) or "",
                  dims_used_note(4, lang) or "",
                  dimension_status_note(DimensionScore("revisions", "accumulating", None, None, [], days_accumulated=12), lang) or "",
                  dimension_status_note(DimensionScore("growth", "unavailable", None, None, []), lang) or ""]
    return texts


def test_no_forbidden_words_anywhere():
    bad = [(t, contains_forbidden(t)) for t in _all_texts() if contains_forbidden(t)]
    assert bad == []


def test_forbidden_detector_itself():
    assert contains_forbidden("建议买入") == ["买入"]
    assert contains_forbidden("Strong BUY rating") == ["buy"]
    assert contains_forbidden("large buybacks") == []  # 词边界：回购不是买卖措辞
    assert contains_forbidden("数据来自 FMP") == ["FMP"]
    assert contains_forbidden("营收同比 +94%") == []


def _sm(key, value, p, grade="A"):
    return ScoredMetric(key, MetricValue(value, "ok", [("price", 227.21), ("eps_ntm", 5.51)], "div"), "ok", p, grade, 100)


def test_key_fact_wording():
    assert key_fact_text(_sm("rev_yoy", 0.94, 99), "zh") == "营收同比 +94%，高于板块 99% 的公司"
    # 估值越低越好：百分位 12 表示数值高于 88% 的公司
    assert key_fact_text(_sm("pe_fwd", 41.2, 12), "zh") == "前瞻市盈率 41.2，高于板块 88% 的公司"
    assert key_fact_text(_sm("rev_yoy", 0.02, 10), "zh") == "营收同比 +2.0%，低于板块 90% 的公司"
    assert key_fact_text(_sm("rev_yoy", 0.94, 99), "en") == "Revenue YoY +94%, higher than 99% of sector peers"


def test_position_and_expression():
    sm = _sm("pe_fwd", 41.2, 12, "F")
    assert position_text(sm, "zh") == "高于 88% 的同板块公司 → 百分位 12 → F"
    assert metric_expression("pe_fwd", sm.mv, "zh") == "股价 227.21 ÷ NTM EPS 预期 5.51 = 41.2"


def test_dimension_formula():
    d = DimensionScore("valuation", "ok", 19.6, "F", [_sm("pe_ttm", 1, 12), _sm("pb", 1, 27.2)])
    assert dimension_formula(d) == "(12 + 27) ÷ 2 = 19.6 → F"


@pytest.mark.parametrize(("v", "lang", "out"), [(5.5e12, "zh", "5.50 万亿"), (9.6e10, "zh", "960.0 亿"),
                                               (9.6e10, "en", "96.0B"), (-2e9, "en", "-2.0B")])
def test_fmt_money(v, lang, out):
    assert fmt_money(v, lang) == out


def test_fmt_metric_value():
    assert fmt_metric_value("pe_ttm", 28.72) == "28.7"
    assert fmt_metric_value("peg_fwd", 0.239) == "0.24"
    assert fmt_metric_value("gross_m", 0.747) == "75%"
    assert fmt_metric_value("r12m", -0.086) == "-8.6%"
