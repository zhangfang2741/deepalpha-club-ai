"""量化研究文案（zh / en）。只描述数值与在同板块中的位置，不出现买卖导向措辞与数据供应商名。

禁用词由 tests/services/quant_research/test_copy.py 与 golden 测试守护。
"""

from __future__ import annotations

import re
from typing import Literal

from app.services.quant_research.metrics import DIMENSION_NAMES, INPUT_LABELS, METRICS, MetricValue
from app.services.quant_research.scoring import DimensionScore, OverallScore, ScoredMetric
from app.services.quant_research.stage import STAGE_NAMES

Lang = Literal["zh", "en"]

FORBIDDEN: list[str] = [
    "买入", "卖出", "推荐", "看多", "看空", "强力", "上涨空间", "抄底", "逃顶",
    "buy", "sell", "recommend", "bullish", "bearish", "upside", "outperform", "underperform",
    "FMP", "Financial Modeling Prep", "financialmodelingprep", "akshare", "东方财富", "东财", "同花顺", "Yahoo",
]

DISCLAIMER = {
    "zh": "量化研究为基于公开财务数据的统计比较，不构成投资建议。",
    "en": "Quant research is a statistical comparison based on public financial data and is not investment advice.",
}

DIMENSION_DESC: dict[str, tuple[str, str]] = {
    "valuation": ("股价相对利润、营收、现金流、资产的倍数", "Price relative to earnings, sales, cash flow and assets"),
    "growth": ("营收与利润的历史及预期增速", "Historical and expected growth of revenue and earnings"),
    "profitability": ("利润率与资本回报", "Margins and returns on capital"),
    "momentum": ("最近 3 ~ 12 个月的股价涨跌", "Price change over the last 3 to 12 months"),
    "revisions": ("分析师一致预期的近期调整", "Recent changes in analyst consensus estimates"),
}

STAGE_NOTES: dict[str, tuple[str, str]] = {
    "intro": ("这一阶段的公司利润类指标通常为负，常见的关注点是营收增速、毛利率和现金消耗",
              "Earnings-based metrics are usually negative at this stage; revenue growth, gross margin and cash burn are common focus points"),
    "growth": ("这一阶段常见的关注点是营收和利润增速、利润率的变化",
               "Common focus points at this stage are revenue and earnings growth and margin trends"),
    "mature": ("这一阶段常见的关注点是估值、自由现金流和资本回报",
               "Common focus points at this stage are valuation, free cash flow and returns on capital"),
    "shakeout": ("现金流结构处在变化中，各维度等级可能波动较大",
                 "The cash-flow pattern is in transition; grades may fluctuate more than usual"),
    "decline": ("这一阶段常见的关注点是现金流和资产负债状况",
                "Common focus points at this stage are cash flow and the balance sheet"),
}

_PER_SHARE = {"price", "eps_ttm", "eps_ttm_prev", "eps_ntm", "eps_fy1", "eps_fy2", "eps_fy0",
              "close_now", "close_then", "est_new", "est_old"}
_PLAIN = {"pe", "growth_pct"}
_SIGNED_DIMS = {"growth", "momentum", "revisions"}


def _i(lang: Lang, zh: str, en: str) -> str:
    return zh if lang == "zh" else en


# ---------- 数值格式 ----------

def fmt_money(v: float, lang: Lang) -> str:
    a = abs(v)
    if lang == "zh":
        if a >= 1e12:
            return f"{v / 1e12:.2f} 万亿"
        if a >= 1e8:
            return f"{v / 1e8:.1f} 亿"
        if a >= 1e4:
            return f"{v / 1e4:.1f} 万"
        return f"{v:.0f}"
    if a >= 1e12:
        return f"{v / 1e12:.2f}T"
    if a >= 1e9:
        return f"{v / 1e9:.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:.1f}M"
    return f"{v:.0f}"


def fmt_input(label: str, v: float | None, lang: Lang) -> str:
    if v is None:
        return "—"
    if label in _PER_SHARE:
        return f"{v:.2f}"
    if label in _PLAIN:
        return f"{v:.1f}"
    return fmt_money(v, lang)


def fmt_metric_value(key: str, v: float | None) -> str:
    """指标数值显示：倍数 1 位小数（PEG、资产周转 2 位）；百分比取整，增长 / 动量 / 修正带符号。"""
    if v is None:
        return "—"
    d = METRICS[key]
    if d.unit == "x":
        return f"{v:.2f}" if key.startswith("peg") or key == "asset_turn" else f"{v:.1f}"
    pct = v * 100
    if d.dimension in _SIGNED_DIMS:
        return f"{pct:+.1f}%" if abs(pct) < 10 else f"{pct:+.0f}%"
    return f"{pct:.1f}%" if abs(pct) < 10 else f"{pct:.0f}%"


def metric_name(key: str, lang: Lang) -> str:
    d = METRICS[key]
    return d.name_zh if lang == "zh" else d.name_en


def label(name: str, lang: Lang) -> str:
    zh, en = INPUT_LABELS[name]
    return _i(lang, zh, en)


# ---------- 位置描述 ----------

def share_below(sm: ScoredMetric) -> float | None:
    """同板块中数值比它低的公司占比（与方向无关，纯数值位置）。"""
    if sm.percentile is None or sm.mv.status != "ok":
        return None
    lower_better = METRICS[sm.key].direction == "lower_better"
    return 100 - sm.percentile if lower_better else sm.percentile


def position_phrase(sm: ScoredMetric, lang: Lang) -> str:
    below = share_below(sm)
    if below is None:
        return ""
    if below >= 50:
        return _i(lang, f"高于板块 {below:.0f}% 的公司", f"higher than {below:.0f}% of sector peers")
    return _i(lang, f"低于板块 {100 - below:.0f}% 的公司", f"lower than {100 - below:.0f}% of sector peers")


def key_fact_text(sm: ScoredMetric, lang: Lang) -> str:
    name = metric_name(sm.key, lang)
    if sm.mv.status == "not_meaningful":
        return _i(lang, f"{name}无意义（利润为负），按最差计", f"{name} is not meaningful (negative earnings), scored as lowest")
    sep = "，" if lang == "zh" else ", "
    return f"{name} {fmt_metric_value(sm.key, sm.mv.value)}{sep}{position_phrase(sm, lang)}"


def position_text(sm: ScoredMetric, lang: Lang) -> str | None:
    if sm.percentile is None or sm.grade is None:
        return None
    p = f"{sm.percentile:.0f}"
    if sm.mv.status == "not_meaningful":
        return _i(lang, f"无意义，按最差计 → 百分位 0 → {sm.grade}",
                  f"Not meaningful, scored as lowest → percentile 0 → {sm.grade}")
    below = share_below(sm)
    if below is not None and below >= 50:
        head = _i(lang, f"高于 {below:.0f}% 的同板块公司", f"Higher than {below:.0f}% of sector peers")
    else:
        head = _i(lang, f"低于 {100 - (below or 0):.0f}% 的同板块公司", f"Lower than {100 - (below or 0):.0f}% of sector peers")
    return _i(lang, f"{head} → 百分位 {p} → {sm.grade}", f"{head} → percentile {p} → {sm.grade}")


# ---------- 算式 ----------

def metric_expression(key: str, mv: MetricValue, lang: Lang) -> str:
    ins = mv.inputs
    if len(ins) < 2:
        return ""
    (la, a), (lb, b) = ins[0], ins[1]
    A, B = f"{label(la, lang)} {fmt_input(la, a, lang)}", f"{label(lb, lang)} {fmt_input(lb, b, lang)}"
    result = fmt_metric_value(key, mv.value) if mv.value is not None else "—"
    if mv.op == "div" or mv.op == "peg":
        return f"{A} ÷ {B} = {result}"
    if mv.op in ("growth", "ret"):
        return f"{A} ÷ {B} − 1 = {result}"
    if mv.op == "cagr3":
        return f"({A} ÷ {B})^(1/3) − 1 = {result}"
    if mv.op == "change":
        return f"({A} − {fmt_input(lb, b, lang)}) ÷ |{B}| = {result}"
    return ""


def dimension_formula(dim: DimensionScore) -> str | None:
    ps = [s.percentile for s in dim.metrics if s.percentile is not None]
    if dim.score is None or not ps:
        return None
    return f"({' + '.join(f'{p:.0f}' for p in ps)}) ÷ {len(ps)} = {dim.score:.1f} → {dim.grade}"


# ---------- 状态说明 ----------

def metric_status_note(sm: ScoredMetric, lang: Lang) -> str | None:
    st, mv = sm.status, sm.mv
    if st == "ok":
        return None
    if st == "insufficient_sample":
        return _i(lang, "板块样本不足 20 家，不参与计算", "Fewer than 20 sector peers, excluded")
    if st == "not_meaningful":
        return _i(lang, "分母为负（利润或现金流为负），无意义，按最差计",
                  "Negative denominator (losses or negative cash flow): not meaningful, scored as lowest")
    if st == "not_applicable":
        if mv.meta.get("reason") == "financials_revenue_basis":
            return _i(lang, "金融股报表营收与分析师预期口径不同，不适用，不参与计算",
                      "Reported and consensus revenue use different bases for financials; excluded")
        if sm.key in ("pb", "roe"):
            return _i(lang, "股东权益为负（常见于大额回购），不适用，不参与计算",
                      "Negative shareholders' equity (often from large buybacks); excluded")
        if sm.key == "roic":
            return _i(lang, "投入资本为负，不适用，不参与计算", "Negative invested capital; excluded")
        return _i(lang, "企业价值为负（现金多于市值与负债之和），不适用，不参与计算",
                  "Negative enterprise value (cash exceeds market cap plus debt); excluded")
    return _i(lang, "数据缺失或增长基数为负，不参与计算", "Data missing or negative growth base; excluded")


def dimension_status_note(dim: DimensionScore, lang: Lang) -> str | None:
    if dim.status == "accumulating":
        d = dim.days_accumulated or 0
        return _i(lang, f"修正历史积累中（已 {d} 天）", f"Building revision history ({d} days so far)")
    if dim.status == "unavailable":
        return _i(lang, "可用指标不足一半，暂无等级", "Fewer than half of the metrics are available; no grade")
    return None


def dimension_name(key: str, lang: Lang) -> str:
    zh, en = DIMENSION_NAMES[key]
    return _i(lang, zh, en)


def dimension_desc(key: str, lang: Lang) -> str:
    zh, en = DIMENSION_DESC[key]
    return _i(lang, zh, en)


def overall_text(o: OverallScore, lang: Lang) -> str | None:
    if o.score is None or o.universe_percentile is None:
        return None
    top = max(1, round(100 - o.universe_percentile))
    return _i(lang, f"综合分 {o.score:.1f} · 标普1500 前 {top}%", f"Composite {o.score:.1f} · top {top}% of S&P 1500")


def overall_note(o: OverallScore, lang: Lang) -> str | None:
    if o.grade is None and o.extra.get("reason") == "few_analysts":
        return _i(lang, "分析师覆盖不足 3 位，不给综合等级", "Fewer than 3 covering analysts; no composite grade")
    if o.capped and o.cap_dimension:
        n = dimension_name(o.cap_dimension, lang)
        return _i(lang, f"{n}为 F，综合等级最高 C+", f"{n} is F, so the composite grade is capped at C+")
    return None


def dims_used_note(used: int, lang: Lang) -> str | None:
    if used >= 5:
        return None
    return _i(lang, f"本次综合等级基于 {used} 个维度", f"Composite grade based on {used} dimensions")


def stage_name(key: str, lang: Lang) -> str:
    zh, en = STAGE_NAMES[key]
    return _i(lang, zh, en)


def stage_note(key: str, unprofitable: bool, lang: Lang) -> str:
    zh, en = STAGE_NOTES[key]
    note = _i(lang, zh, en)
    if unprofitable:
        note += _i(lang, "。尚未盈利，利润类指标按最差计", ". Not yet profitable; earnings-based metrics are scored as lowest")
    return note


def peer_text(sector_name: str, n: int, lang: Lang) -> str:
    return _i(lang, f"与{sector_name}板块 {n} 家公司比", f"Compared with {n} {sector_name} companies")


def contains_forbidden(text: str) -> list[str]:
    low = text.lower()
    hits = []
    for w in FORBIDDEN:
        wl = w.lower()
        if wl.isascii():
            if re.search(rf"\b{re.escape(wl)}\b", low):
                hits.append(w)
        elif wl in low:
            hits.append(w)
    return hits
