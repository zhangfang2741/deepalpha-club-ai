"""基本面动向：每只股票「最近在变好什么」的事实（批量时算好、随结果落库），供「基本面动向雷达」使用。

两类事实，都不是评分、不进综合等级：
1. 预期修正：本财年 EPS 一致预期近 7 / 30 / 90 天的变化率。30 / 90 天直接取 EPS 修正维度里已算好的值
   （自有快照不满 90 天时用外部趋势过渡，口径见 revisions.py）；7 天用自有每日快照（point-in-time）。
2. 质地变化：最近一季与上一季相比（都用最近 12 个月口径），营收同比、毛利率、经营利润率、自由现金流利润率各变了几个百分点。
   上一季 = 把季度序列整体往前挪一季重算同一套指标，所以和页面上的指标口径完全一致；
   资产负债表只有最新一期，所以不比较 ROE / ROA / ROIC 这类用到资产负债表的指标。

都是现成数据，上线后跑一次批量就有，不需要等几个月攒历史。纯函数。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from app.schemas.quant_research import TrendFacts
from app.services.quant_research.inputs import StockInputs, analyst_count
from app.services.quant_research.metrics import MetricValue, compute_metrics
from app.services.quant_research.revisions import EstimatePoint, change, value_at

WEEK_DAYS = 7
WEEK_TOLERANCE_DAYS = 3   # 7 天前那份快照允许差几天（周末 / 节假日没有快照）
_QUALITY_KEYS = ("rev_yoy", "gross_m", "ebit_m", "fcf_m")


def _pp(cur: MetricValue | None, prev: MetricValue | None) -> float | None:
    if cur is None or prev is None or cur.status != "ok" or prev.status != "ok":
        return None
    if cur.value is None or prev.value is None:
        return None
    return round((cur.value - prev.value) * 100, 2)


def _ratio(mv: MetricValue | None) -> float | None:
    return round(mv.value, 4) if mv is not None and mv.status == "ok" and mv.value is not None else None


def eps_week_change(inp: StockInputs, history: list[EstimatePoint]) -> float | None:
    """本财年 EPS 一致预期近 7 天变化率（自有快照）；缺任一端返回 None。"""
    fy1 = inp.fy1
    fiscal = fy1.get("date") if fy1 else None
    if not fiscal:
        return None
    now = value_at(history, fiscal, inp.as_of, "eps_avg", tolerance_days=WEEK_TOLERANCE_DAYS)
    old = value_at(history, fiscal, inp.as_of - timedelta(days=WEEK_DAYS), "eps_avg",
                   tolerance_days=WEEK_TOLERANCE_DAYS)
    c = change(now, old)
    return round(c, 4) if c is not None else None


def trend_facts(inp: StockInputs, history: list[EstimatePoint], metrics: dict[str, MetricValue]) -> TrendFacts:
    """一只股票的基本面动向事实。metrics = 本次评估已算好的全部指标（含 EPS 修正）。"""
    prev_metrics: dict[str, MetricValue] = {}
    if len(inp.quarters_income) > 1:
        prev = replace(inp, quarters_income=inp.quarters_income[1:], quarters_cash=inp.quarters_cash[1:])
        try:
            prev_metrics = compute_metrics(prev)
        except Exception:  # noqa: BLE001 上一季数据残缺时只是没有质地变化，不影响本股评分
            prev_metrics = {}
    prev_period = inp.quarters_income[1].get("date") if len(inp.quarters_income) > 1 else None
    return TrendFacts(
        n_analysts=analyst_count(inp.fy1),
        eps_rev_7d=eps_week_change(inp, history),
        eps_rev_30d=_ratio(metrics.get("eps_fy1_30d")),
        eps_rev_90d=_ratio(metrics.get("eps_fy1_90d")),
        quality_period=inp.quarters_income[0].get("date") if inp.quarters_income else None,
        quality_prev_period=prev_period,
        filing_date=inp.filing_date,
        d_rev_yoy_pp=_pp(metrics.get("rev_yoy"), prev_metrics.get("rev_yoy")),
        d_gross_m_pp=_pp(metrics.get("gross_m"), prev_metrics.get("gross_m")),
        d_ebit_m_pp=_pp(metrics.get("ebit_m"), prev_metrics.get("ebit_m")),
        d_fcf_m_pp=_pp(metrics.get("fcf_m"), prev_metrics.get("fcf_m")),
    )
