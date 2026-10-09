"""量化研究文案（zh / en）。只描述数值与在同板块中的位置，不出现买卖导向措辞与数据供应商名。

禁用词由 tests/services/quant_research/test_copy.py 与 golden 测试守护。
"""

from __future__ import annotations

import re
from typing import Literal

from app.services.quant_research.markets import profile
from app.services.quant_research.metrics import DIMENSION_NAMES, INPUT_LABELS, METRICS, STABILITY_KEYS, MetricValue
from app.services.quant_research.scoring import DimensionScore, OverallScore, ScoredMetric
from app.services.quant_research.stage import STAGE_NAMES

Lang = Literal["zh", "en"]

FORBIDDEN: list[str] = [
    "买入", "卖出", "推荐", "看多", "看空", "强力", "上涨空间", "抄底", "逃顶",
    "buy", "sell", "recommend", "bullish", "bearish", "upside", "outperform", "underperform",
    "FMP", "Financial Modeling Prep", "financialmodelingprep", "akshare", "东方财富", "东财", "同花顺", "Yahoo",
    "经济通", "ETNet", "新浪", "雅虎", "Eastmoney",
]

DISCLAIMER = {
    "zh": "基本面研究为基于公开财务数据的统计比较，不构成投资建议。",
    "en": "Fundamental research is a statistical comparison based on public financial data and is not investment advice.",
}

DIMENSION_DESC: dict[str, tuple[str, str]] = {
    "valuation": ("股价相对利润、营收、现金流、资产的倍数", "Price relative to earnings, sales, cash flow and assets"),
    "growth": ("营收与利润的历史及预期增速", "Historical and expected growth of revenue and earnings"),
    "profitability": ("利润率与资本回报", "Margins and returns on capital"),
    "momentum": ("最近 3 ~ 12 个月的股价涨跌", "Price change over the last 3 to 12 months"),
    "revisions": ("分析师一致预期的近期调整", "Recent changes in analyst consensus estimates"),
    "stability": ("偿债压力、短期流动性、现金能撑多久与利润的现金含量",
                  "Debt burden, near-term liquidity, cash runway and how much profit turns into cash"),
}

STAGE_NOTES: dict[str, tuple[str, str]] = {
    "intro": ("这一阶段的公司利润类指标通常为负，常见的关注点是营收增速、毛利率和现金消耗",
              "Earnings-based metrics are usually negative at this stage; revenue growth, gross margin and cash burn are common focus points"),
    "growth": ("这一阶段常见的关注点是营收和利润增速、利润率的变化",
               "Common focus points at this stage are revenue and earnings growth and margin trends"),
    "mature": ("这一阶段常见的关注点是估值、自由现金流和资本回报",
               "Common focus points at this stage are valuation, free cash flow and returns on capital"),
    "shakeout": ("营收或经营现金流处在变化中，各维度等级可能波动较大",
                 "Revenue or operating cash flow is in transition; grades may fluctuate more than usual"),
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
    """金额按中文（亿 / 万亿）或英文（M / B / T）缩写。"""
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
    """算式输入值：每股数值 2 位小数，倍数 / 增速 1 位，金额缩写。"""
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
    """指标展示名。"""
    d = METRICS[key]
    return d.name_zh if lang == "zh" else d.name_en


def label(name: str, lang: Lang) -> str:
    """算式输入的标签。"""
    zh, en = INPUT_LABELS[name]
    return _i(lang, zh, en)


def _nm_reason(key: str) -> tuple[str, str]:
    """「无意义」的具体原因（按指标的分母）。"""
    if key.startswith("peg"):
        return "EPS 增速或利润为负", "negative EPS growth or earnings"
    if key == "pcf":
        return "经营现金流为负", "negative operating cash flow"
    if key in ("ps_ttm", "ps_fwd", "ev_sales_ttm", "ev_sales_fwd"):
        return "营收为负", "negative revenue"
    if key == "net_debt_ebitda":
        return "EBITDA 为负而仍有净负债", "negative EBITDA while carrying net debt"
    if key.startswith("ev_ebitda"):
        return "EBITDA 为负", "negative EBITDA"
    if key.startswith("ev_ebit"):
        return "EBIT 为负", "negative EBIT"
    return "利润为负", "negative earnings"


# ---------- 位置描述 ----------

def share_below(sm: ScoredMetric) -> float | None:
    """同板块中数值比它低的公司占比（与方向无关，纯数值位置）。"""
    if sm.percentile is None or sm.mv.status != "ok":
        return None
    lower_better = METRICS[sm.key].direction == "lower_better"
    return 100 - sm.percentile if lower_better else sm.percentile


def position_phrase(sm: ScoredMetric, lang: Lang) -> str:
    """「高于 / 低于板块 x% 的公司」（x 取 1~99）。"""
    below = share_below(sm)
    if below is None:
        return ""
    below = min(max(below, 1.0), 99.0)
    if below >= 50:
        return _i(lang, f"高于板块 {below:.0f}% 的公司", f"higher than {below:.0f}% of sector peers")
    return _i(lang, f"低于板块 {100 - below:.0f}% 的公司", f"lower than {100 - below:.0f}% of sector peers")


def key_fact_text(sm: ScoredMetric, lang: Lang) -> str:
    """维度卡片上的关键事实：指标名 + 数值 + 板块位置。"""
    name = metric_name(sm.key, lang)
    if sm.mv.status == "not_meaningful":
        zh, en = _nm_reason(sm.key)
        return _i(lang, f"{name} 无意义（{zh}），按最差计", f"{name} is not meaningful ({en}), scored as lowest")
    sep = "，" if lang == "zh" else ", "
    return f"{name} {fmt_metric_value(sm.key, sm.mv.value)}{sep}{position_phrase(sm, lang)}"


def position_text(sm: ScoredMetric, lang: Lang) -> str | None:
    """指标详情里的「位置 → 百分位 → 等级」推导。"""
    if sm.percentile is None or sm.grade is None:
        return None
    p = f"{sm.percentile:.0f}"
    if sm.mv.status == "not_meaningful":
        return _i(lang, f"无意义，按最差计 → 百分位 0 → {sm.grade}",
                  f"Not meaningful, scored as lowest → percentile 0 → {sm.grade}")
    below = min(max(share_below(sm) or 0.0, 1.0), 99.0)
    if below >= 50:
        head = _i(lang, f"高于 {below:.0f}% 的同板块公司", f"Higher than {below:.0f}% of sector peers")
    else:
        head = _i(lang, f"低于 {100 - below:.0f}% 的同板块公司", f"Lower than {100 - below:.0f}% of sector peers")
    return _i(lang, f"{head} → 百分位 {p} → {sm.grade}", f"{head} → percentile {p} → {sm.grade}")


# ---------- 算式 ----------

def metric_expression(key: str, mv: MetricValue, lang: Lang) -> str:
    """带真实数字的算式，如「股价 227.21 ÷ NTM EPS 预期 13.67 = 16.6」。"""
    ins = mv.inputs
    if len(ins) < 2:
        return ""
    (la, a), (lb, b) = ins[0], ins[1]
    A, B = f"{label(la, lang)} {fmt_input(la, a, lang)}", f"{label(lb, lang)} {fmt_input(lb, b, lang)}"
    result = fmt_metric_value(key, mv.value) if mv.value is not None else "—"
    # 财务稳健：「没有压力」与「触顶」的约定值要把原因写出来，否则算式和结果对不上
    if mv.meta.get("net_cash"):
        return _i(lang, f"{A} ≤ 0（现金多于负债）→ {result}", f"{A} ≤ 0 (cash exceeds debt) → {result}")
    if mv.meta.get("no_interest"):
        return _i(lang, f"{B}（没有利息支出）→ 记上限 {result}", f"{B} (no interest expense) → capped at {result}")
    if mv.meta.get("self_funding"):
        fcf = fmt_input(lb, -b if b is not None else None, lang)
        return _i(lang, f"最近 12 个月自由现金流 {fcf}（为正，不烧钱）→ 记上限 {result} 年",
                  f"Trailing 12-month free cash flow {fcf} (positive, no burn) → capped at {result} years")
    if mv.op == "div" and key in ("interest_cov", "runway_years") and a is not None and b and mv.value is not None:
        raw = a / b
        if raw > mv.value + 1e-9:  # 被上限截断
            unit_zh, unit_en = ("", "") if key == "interest_cov" else (" 年", " years")
            return _i(lang, f"{A} ÷ {B} = {raw:.1f}{unit_zh}，超过上限按 {result}{unit_zh} 计",
                      f"{A} ÷ {B} = {raw:.1f}{unit_en}, above the cap, counted as {result}{unit_en}")
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
    """维度分算式「(p1 + p2 + …) ÷ n = 分 → 等级」。"""
    ps = [s.percentile for s in dim.metrics if s.percentile is not None]
    if dim.score is None or not ps:
        return None
    return f"({' + '.join(f'{p:.0f}' for p in ps)}) ÷ {len(ps)} = {dim.score:.1f} → {dim.grade}"


# ---------- 状态说明 ----------

def metric_status_note(sm: ScoredMetric, lang: Lang) -> str | None:
    """指标特殊状态的说明（无意义 / 不适用 / 缺失 / 样本不足）。"""
    st, mv = sm.status, sm.mv
    if st == "ok":
        return None
    if st == "insufficient_sample":
        return _i(lang, "板块样本不足 20 家，不参与计算", "Fewer than 20 sector peers, excluded")
    if st == "not_meaningful":
        zh, en = _nm_reason(sm.key)
        return _i(lang, f"{zh}，无意义，按最差计", f"{en[0].upper()}{en[1:]}: not meaningful, scored as lowest")
    if st == "not_applicable":
        if mv.meta.get("reason") == "financials_cash_flow":
            return _i(lang, "金融股经营现金流含存贷款变动，不适用，不参与计算",
                      "Operating cash flow of financials includes deposit and loan flows; excluded")
        if mv.meta.get("reason") == "financials_structure":
            return _i(lang, "银行、券商、保险没有一般企业的有息负债与营业成本口径，不适用，不参与计算",
                      "Banks, brokers and insurers have no comparable debt or cost-of-sales basis; excluded")
        if mv.meta.get("reason") == "financials_balance_sheet":
            return _i(lang, "银行、保险等金融公司的负债本身就是经营的一部分，偿债口径不可比，不适用，不参与计算",
                      "For banks and insurers debt is part of the business itself, so debt-burden metrics are not comparable; excluded")
        if sm.key == "cfo_ni":
            return _i(lang, "净利润为负，比值没有意义，不适用，不参与计算",
                      "Net income is negative, so the ratio is meaningless; excluded")
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
    if sm.key in STABILITY_KEYS:
        return _i(lang, "报表里缺少所需数据，不参与计算", "Required statement data is not available; excluded")
    return _i(lang, "数据缺失或增长基数为负，不参与计算", "Data missing or negative growth base; excluded")


def dimension_status_note(dim: DimensionScore, lang: Lang) -> str | None:
    """维度状态说明（积累中 / 暂无等级）。"""
    if dim.status == "accumulating":
        d = dim.days_accumulated or 0
        return _i(lang, f"修正历史积累中（已 {d} 天）", f"Building revision history ({d} days so far)")
    if dim.status == "unavailable":
        if dim.metrics and all(m.status == "not_applicable" for m in dim.metrics):
            return _i(lang, "此维度不适用于这类公司，不参与综合分", "Not applicable to this kind of company; left out of the composite")
        return _i(lang, "可用指标太少（不足三分之一），暂无等级", "Too few metrics available (under one third); no grade")
    return None


def dimension_name(key: str, lang: Lang) -> str:
    """维度展示名。"""
    zh, en = DIMENSION_NAMES[key]
    return _i(lang, zh, en)


def dimension_desc(key: str, lang: Lang) -> str:
    """维度的一句话说明。"""
    zh, en = DIMENSION_DESC[key]
    return _i(lang, zh, en)


def overall_text(o: OverallScore, lang: Lang, market: str = "us") -> str | None:
    """综合分与在比较样本（美股标普1500 / A 股市值前 1800 / 港股样本）中的排位。"""
    if o.score is None or o.universe_percentile is None:
        return None
    uni = profile(market).universe(lang)
    if o.universe_percentile >= 50:
        top = max(1, round(100 - o.universe_percentile))
        return _i(lang, f"综合分 {o.score:.1f} · {uni} 前 {top}%", f"Composite {o.score:.1f} · top {top}% of {uni}")
    bottom = max(1, round(o.universe_percentile))
    return _i(lang, f"综合分 {o.score:.1f} · {uni} 后 {bottom}%",
              f"Composite {o.score:.1f} · bottom {bottom}% of {uni}")


def overall_note(o: OverallScore, lang: Lang) -> str | None:
    """综合等级的附加说明（封顶 / 分析师不足）。"""
    if o.grade is None and o.extra.get("reason") == "few_analysts":
        return _i(lang, "分析师覆盖不足 3 位，不给综合等级", "Fewer than 3 covering analysts; no composite grade")
    if o.capped and o.cap_dimension:
        n = dimension_name(o.cap_dimension, lang)
        return _i(lang, f"{n}为 F，综合等级最高 C+", f"{n} is F, so the composite grade is capped at C+")
    return None


def dims_used_note(used: int, lang: Lang) -> str | None:
    """少于 5 个维度参与时的说明（金融股没有财务稳健、新股还在积累 EPS 修正，常态是 5 个）。"""
    if used >= 5:
        return None
    return _i(lang, f"本次综合等级基于 {used} 个维度", f"Composite grade based on {used} dimensions")


def stage_name(key: str, lang: Lang) -> str:
    """阶段展示名。"""
    zh, en = STAGE_NAMES[key]
    return _i(lang, zh, en)


def stage_note(key: str, unprofitable: bool, lang: Lang) -> str:
    """阶段提示（中性表述）。"""
    zh, en = STAGE_NOTES[key]
    note = _i(lang, zh, en)
    if unprofitable:
        note += _i(lang, "。尚未盈利，利润类指标按最差计", ". Not yet profitable; earnings-based metrics are scored as lowest")
    return note


def peer_text(sector_name: str, n: int, lang: Lang, in_universe: bool = True, market: str = "us") -> str:
    """比较对象说明。"""
    base = _i(lang, f"与{sector_name}板块 {n} 家公司比", f"Compared with {n} {sector_name} companies")
    if in_universe:
        return base
    uni = profile(market).universe(lang)
    return base + _i(lang, f"（本股不在{uni}样本内，按该板块分布定位）",
                     f" (not in the {uni} sample; placed against the sector distribution)")


def currency_note(fx: dict | None, lang: Lang) -> str | None:
    """港股金额换算说明：报表原为人民币口径、预期为申报币种，统一折成港元（股价币种）。"""
    if not fx or not fx.get("hkd_cny"):
        return None
    rate = 1 / fx["hkd_cny"]
    zh = f"财务数据按 1 人民币 = {rate:.4f} 港元折算为港元"
    en = f"Financials converted to HKD at 1 CNY = {rate:.4f} HKD"
    cur = fx.get("estimate_currency")
    if cur and cur not in ("CNY", "HKD"):
        zh += f"；分析师预期原为 {cur}，按当日汇率折算"
        en += f"; analyst estimates converted from {cur} at today's rate"
    return _i(lang, zh, en)


def contains_forbidden(text: str) -> list[str]:
    """返回文本中出现的禁用词（英文按词边界、不区分大小写）。"""
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
