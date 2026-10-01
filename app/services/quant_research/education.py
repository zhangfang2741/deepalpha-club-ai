"""指标教育文案；计算口径以 metrics.py 为准，不参与评分。

估值解释参考：
https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples
https://www.finra.org/investors/investing/investment-products/stocks/evaluating-stocks
"""

from app.schemas.quant_research import MetricInterpretation, QuantResearchOut
from app.services.quant_research.formulas import metric_calculation
from app.services.quant_research.glossary import input_hint, plain_language
from app.services.quant_research.metrics import INPUT_LABELS, METRICS, MetricDef

# 同一经济含义共用解读，具体期间与分母由每项指标的定义明确。
_GUIDANCE: dict[str, tuple[str, str, str, str]] = {
    "pe": (
        "衡量每一元盈利需要付出的价格，结合盈利稳定性判断是否值得。",
        "低倍数也可能来自周期高点或盈利即将下滑；亏损时不能按负市盈率判断便宜。",
        "Measures the price paid for each unit of earnings; assess how sustainable those earnings are.",
        "A low multiple may reflect peak-cycle profits or expected declines. Negative P/E does not mean cheap.",
    ),
    "peg": (
        "把盈利估值与增长放在一起看，检查价格是否过度透支成长。",
        "增速以百分数代入，例如 20% 用 20；接近零时比值敏感，PEG 小于 1 也不自动代表低估。",
        "Relates the earnings multiple to growth to assess how much growth is priced in.",
        "Enter growth as a percent number: 20% means 20. Near-zero growth distorts PEG; below 1 is not proof of undervaluation.",
    ),
    "sales": (
        "衡量为每一元收入支付的价格，并结合利润率看收入最终能留下多少利润。",
        "收入不是利润。低利润率公司可能合理地享有更低倍数，不能只比较营收倍数。",
        "Measures the price paid per unit of revenue; margins show how much becomes profit.",
        "Revenue is not profit. A lower-margin business may deserve a lower sales multiple.",
    ),
    "ebitda": (
        "用企业整体价格比较息税折旧摊销前利润，辅助比较不同融资结构的公司。",
        "EBITDA 没有扣除资本开支，也不等于可分配现金；重资产公司还要检查自由现金流。",
        "Compares enterprise value with earnings before interest, taxes, depreciation and amortization.",
        "EBITDA excludes capital spending and is not distributable cash; also examine free cash flow.",
    ),
    "ebit": (
        "用企业整体价格比较扣除折旧后的息税前利润，观察经营收益的购买成本。",
        "仍需考虑税、再投资和营运资金需求；应与业务及资本结构相近的公司比较。",
        "Compares enterprise value with operating earnings after depreciation, before interest and tax.",
        "Taxes, reinvestment and working capital still matter; compare similar businesses.",
    ),
    "pb": (
        "衡量为每一元账面净资产付出的价格，结合资产质量与股东回报率理解。",
        "账面净资产不是清算价值；低于 1 倍可能反映资产减值风险，高回报的轻资产公司也可能长期高于 1 倍。",
        "Measures the price paid per unit of book equity; interpret alongside asset quality and ROE.",
        "Book equity is not liquidation value. Below 1 may reflect impaired assets; asset-light firms may trade above 1.",
    ),
    "pcf": (
        "比较为经营活动产生的现金支付的价格，辅助检验利润的现金含量。",
        "经营现金流未扣资本开支，也可能受收付款时点影响；应结合多年自由现金流。",
        "Measures the price paid for operating cash flow and helps assess cash backing for earnings.",
        "Operating cash flow excludes capital spending and varies with payment timing; examine several years of free cash flow.",
    ),
    "growth": (
        "观察生意是否扩大，以及增长能否转化为长期每股现金收益。",
        "低基数、并购或一次性收益可能放大增速；增长还需与投入资本回报、估值一起看。",
        "Tracks business expansion and whether growth can translate into long-term cash earnings per share.",
        "Low bases, acquisitions and one-off gains can inflate growth; assess returns on capital and valuation too.",
    ),
    "margin": (
        "观察每一元收入能留下多少收益，持续性和同业差异有助于理解竞争力。",
        "不同商业模式利润率差异很大；一次性项目和会计口径会影响结果，应观察多年趋势。",
        "Shows earnings retained per unit of revenue; persistence and peer comparisons help assess competitiveness.",
        "Business models, one-off items and accounting policies affect margins; examine multi-year trends.",
    ),
    "fcf_m": (
        "观察收入扣除经营现金支出和资本开支后，能留下多少自由现金。",
        "单年偏低可能来自扩产，偏高也可能来自推迟投资；需判断维持业务所需的长期投入。",
        "Shows cash retained from revenue after operating cash outflows and capital spending.",
        "Expansion may lower the ratio, while delayed investment may raise it; assess sustainable reinvestment needs.",
    ),
    "roe": (
        "衡量账面股东资本创造利润的效率，长期稳定的回报有助于理解复利能力。",
        "高杠杆或回购压低权益也会抬高 ROE；本页分母使用报表期末权益，而非期初期末平均值。",
        "Measures profit generated on book equity and helps assess long-term compounding capacity.",
        "Leverage or buybacks can inflate ROE. This model uses period-end equity, not average equity.",
    ),
    "roa": (
        "衡量每一元资产创造净利润的能力，辅助观察资产使用效率。",
        "轻重资产行业不宜直接比较；本页使用报表期末总资产，需结合杠杆与资产周转。",
        "Measures net profit generated per unit of assets and helps assess asset efficiency.",
        "Compare similar asset intensity. This model uses period-end assets; consider leverage and turnover.",
    ),
    "roic": (
        "观察投入生意的资本创造多少税后经营收益，持续超过资本成本才可能创造价值。",
        "本页用期末负债加权益减现金作分母；税率缺失时用 21%，可用税率限制在 0% 至 50%。",
        "Measures after-tax operating returns on invested capital; sustained returns above capital cost can create value.",
        "Uses period-end debt plus equity minus cash. Missing tax rates default to 21%; available rates are clamped to 0–50%.",
    ),
    "asset_turn": (
        "观察每一元资产带来多少收入，与利润率一起理解资本使用效率。",
        "高周转不等于高利润；本页使用期末资产，应结合利润率及行业商业模式比较。",
        "Measures revenue generated per unit of assets; combine with margins to assess capital efficiency.",
        "High turnover does not imply high profit. Uses period-end assets; compare margins and business models.",
    ),
    "momentum": (
        "观察市场过去一段时间如何定价，作为价格趋势的辅助信息。",
        "涨幅不是内在价值增长，也不能证明便宜；价值判断仍需回到盈利、现金流与支付价格。",
        "Shows recent market pricing as supporting information about price trends.",
        "Price appreciation is not intrinsic-value growth or evidence of cheapness; assess earnings, cash flow and price.",
    ),
    "revisions": (
        "观察分析师对同一财年的预期是否改善，帮助跟踪估值所依赖的假设。",
        "变化率 =（当前预期 − 历史预期）÷ |历史预期| × 100%。比较同一财年；预期不是实际业绩，历史不足时不评分。",
        "Tracks changes in expectations for the same fiscal year to monitor valuation assumptions.",
        "Change = (current − historical estimate) / |historical estimate| × 100%. Compare the same fiscal year; forecasts are not actuals. Insufficient history is unscored.",
    ),
}


def metric_interpretation(metric: MetricDef, lang: str) -> MetricInterpretation:
    """为全部指标提供独立可读的定义、投资含义与适用边界。"""
    key = metric.key
    family = metric.dimension
    if family == "valuation":
        if key.startswith("peg"):
            family = "peg"
        elif key.startswith("pe"):
            family = "pe"
        elif key.startswith(("ps", "ev_sales")):
            family = "sales"
        elif key.startswith("ev_ebitda"):
            family = "ebitda"
        elif key.startswith("ev_ebit"):
            family = "ebit"
        else:
            family = key
    elif family == "profitability":
        family = key if key in _GUIDANCE else "margin"
    role_zh, limit_zh, role_en, limit_en = _GUIDANCE[family]
    limit = limit_zh if lang == "zh" else limit_en
    if key.endswith("_fwd"):
        limit += "前瞻数值来自分析师预期，并非已实现业绩。" if lang == "zh" else " Forward inputs are analyst estimates, not realized results."
    full_name, plain, reading = plain_language(metric, lang)
    return MetricInterpretation(
        full_name=full_name,
        plain=plain,
        reading=reading,
        what=metric.desc_zh if lang == "zh" else metric.desc_en,
        role=role_zh if lang == "zh" else role_en,
        threshold=limit,
        calculation=metric_calculation(metric, lang),
    )


def enrich_education(payload: QuantResearchOut, lang: str) -> QuantResearchOut:
    """读取历史缓存时同步更新说明，不重算或修改历史指标值。"""
    i = 0 if lang == "zh" else 1
    label_to_name = {labels[i]: name for name, labels in INPUT_LABELS.items()}
    for dimension in payload.dimensions:
        for group in dimension.groups:
            for metric in group.metrics:
                definition = METRICS.get(metric.key)
                if definition is not None:
                    metric.interpretation = metric_interpretation(definition, lang)
                for item in metric.formula.inputs if metric.formula else []:
                    name = label_to_name.get(item.label)
                    if name is not None:
                        item.hint = input_hint(name, lang)
    return payload
