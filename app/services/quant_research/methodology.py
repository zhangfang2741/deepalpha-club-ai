"""方法说明页（「等级是怎么算的？」）。由规则常量生成，方法调整后 App 不用发版。"""

from __future__ import annotations

from app.schemas.quant_research import (
    GradeBand,
    MethodologyDimension,
    MethodologyMetric,
    MethodologyOut,
)
from app.services.quant_research import copy as tx
from app.services.quant_research.builder import METHODOLOGY_VERSION
from app.services.quant_research.grading import BANDS, HYSTERESIS
from app.services.quant_research.metrics import DIMENSIONS, METRICS, MIN_ANALYSTS
from app.services.quant_research.scoring import CAP_CEILING, CAP_MIN_WEIGHT, MIN_SAMPLE
from app.services.quant_research.stage import STAGE_NAMES, STAGE_WEIGHTS

def _weights_text(lang: int) -> str:
    """各阶段的权重一览，如「成长期 15 / 35 / 20 / 20 / 10」，直接取自 STAGE_WEIGHTS，改表即同步。"""
    return "；".join(
        f"{STAGE_NAMES[stage][lang]} " + " / ".join(f"{STAGE_WEIGHTS[stage][d] * 100:.0f}" for d in DIMENSIONS)
        for stage in STAGE_NAMES)


def _weights_zh() -> str:
    return _weights_text(0)


def _weights_en() -> str:
    return _weights_text(1)


_SECTIONS: list[tuple[tuple[str, str], tuple[str, str]]] = [
    (("和谁比", "Who it is compared with"),
     ("标普1500（标普500 + 中盘400 + 小盘600）按 GICS 11 个板块分组，每项指标只和同板块公司比较。"
      "不在标普1500 内的美股，按它所在板块当天的分布定位。结果只表示在同行中的相对位置，"
      "指标详情里同时给出本股数值与板块中位数。",
      "The S&P 1500 (S&P 500 + MidCap 400 + SmallCap 600) is grouped into the 11 GICS sectors and every metric is "
      "compared only within the sector. US stocks outside the S&P 1500 are placed against that day's sector "
      "distribution. Grades describe relative position among peers; metric details also show the raw value and "
      "the sector median.")),
    (("单项指标", "Single metrics"),
     ("先算本股在板块内的百分位（0~100），方向统一成「越高越好」：估值类越便宜百分位越高。"
      "分母为负且确属没有利润（如亏损导致市盈率为负）按最差计；股东权益为负（常见于大额回购）等不代表经营不佳的情况、"
      f"数据缺失、板块样本少于 {MIN_SAMPLE} 家，都不参与计算。"
      f"前瞻指标用未来 12 个月口径；覆盖的分析师少于 {MIN_ANALYSTS} 位时，预期类指标不参与计算。",
      "Each metric is first turned into a within-sector percentile (0-100), oriented so that higher is better "
      "(cheaper valuation means a higher percentile). Negative denominators that reflect genuine losses are scored "
      "as lowest; cases that do not reflect weak operations (such as negative equity from buybacks), missing data "
      f"and sectors with fewer than {MIN_SAMPLE} peers are excluded. Forward metrics use a next-12-month basis and "
      f"are excluded when fewer than {MIN_ANALYSTS} analysts cover the stock.")),
    (("等级分档", "Grade bands"),
     (f"指标、维度、综合三层用同一把尺子：百分位按 13 档换成 A+ ~ F。为避免边界上的股票每天来回跳，"
      f"百分位越过旧等级边界 {HYSTERESIS:.0f} 分以上才改变等级。",
      f"Metrics, dimensions and the composite share one scale: percentiles map to 13 grades from A+ to F. To avoid "
      f"daily flip-flopping at the edges, a grade only changes once the percentile moves more than {HYSTERESIS:.0f} "
      f"points past the old band.")),
    (("维度分", "Dimension scores"),
     ("维度分 = 该维度内参与计算的指标百分位的等权平均；参与计算的指标不足三分之一（且少于 2 项）时，该维度暂无等级。",
      "A dimension score is the equal-weighted average of its participating metric percentiles; with fewer than "
      "one third of the metrics (and at least 2) available, the dimension has no grade.")),
    (("综合等级", "Composite grade"),
     (f"综合分 = 可用维度分按公司阶段加权平均（权重见「公司阶段」，缺失的维度在其余维度间重新归一）；"
      f"再看综合分在标普1500 全体中的百分位，按同一把尺子定等级。"
      f"综合分里权重不低于 {CAP_MIN_WEIGHT:.0%} 的维度为 F 时，综合等级最高为 {CAP_CEILING}（权重更低的维度没有一票否决权）；"
      f"覆盖的分析师少于 {MIN_ANALYSTS} 位时不给综合等级。",
      f"The composite score is a stage-weighted average of the available dimension scores (weights are listed under "
      f"Company stage; missing dimensions are re-normalized over the rest); its percentile across the whole S&P 1500 "
      f"sets the grade on the same scale. If a dimension carrying at least {CAP_MIN_WEIGHT:.0%} of the weight is F, "
      f"the composite is capped at {CAP_CEILING} (lower-weight dimensions cannot veto); with fewer than "
      f"{MIN_ANALYSTS} covering analysts there is no composite grade.")),
    (("财务稳健", "Financial health"),
     ("看偿债压力、短期流动性、现金能撑多久和利润的现金含量，共五项：净负债 / EBITDA（现金多于负债记 0）、"
      "利息保障倍数（没有利息支出或超过 100 倍记 100）、流动比率、现金可支撑年数（按最近 12 个月自由现金流为负的速度估算，"
      "自由现金流为正的公司不烧钱，记上限 10 年）、经营现金流 / 净利润（净利润为负时不参与）。"
      "「没有压力」一律记成该项的最好值，不当缺失；有净负债而 EBITDA 为负按最差计。"
      "银行、保险等金融公司的负债本身就是经营的一部分，口径不可比，整个维度不参与综合分。"
      "A 股与港股的报表没有流动资产 / 流动负债与利息支出，只用其余三项。"
      "这个维度在每个阶段的权重都不低于一票否决门槛：财务稳健为 F 时，综合等级最高为 C+。",
      "Five metrics on debt burden, near-term liquidity, cash runway and how much profit turns into cash: net debt / "
      "EBITDA (0 when cash exceeds debt), interest coverage (100 when there is no interest expense or it exceeds 100x), "
      "current ratio, cash runway in years (at the trailing 12-month free-cash-flow burn; companies with positive free "
      "cash flow burn nothing and are set to the 10-year cap) and operating cash flow / net income (excluded when net "
      "income is negative). \"No pressure\" is always scored as the best value rather than treated as missing; net debt "
      "with negative EBITDA is scored as lowest. Debt is part of the business for banks and insurers, so the whole "
      "dimension is left out for them. A-share and Hong Kong statements lack current assets / liabilities and interest "
      "expense, so only the other three are used. This dimension's weight is above the veto threshold in every stage: "
      "a financial-health F caps the composite at C+.")),
    (("EPS 修正", "EPS revisions"),
     ("每天保存一次分析师一致预期，比较当前值与 30 / 90 天前的值；亏损收窄算上修。"
      "历史不足 30 天时该维度显示「积累中」，综合等级基于其余维度。本维度用一致预期均值的变化，"
      "而不是上调 / 下调的分析师人数。",
      "Analyst consensus is saved daily and compared with its value 30 and 90 days earlier; a narrowing loss counts "
      "as an upward revision. With under 30 days of history the dimension shows as building, and the composite uses "
      "the other dimensions. The change in the consensus mean is used rather than counts of raising or cutting "
      "analysts.")),
    (("公司阶段", "Company stage"),
     ("以营收增速为主、经营现金流为辅：营收同比 ≥ 15% 且 3 年复合 ≥ 10%（不足 3 年只看同比）为高增长，"
      "经营现金流为正是成长期、否则初创期；营收同比 ≤ −5% 时经营现金流为正是调整期、否则收缩期；"
      "其余经营现金流为正是成熟期、否则调整期。营收同比刚好越过门槛时，上期所在的阶段多保留 2 个百分点，避免来回切换。"
      "阶段决定六个维度在综合分里的权重（估值 / 成长 / 盈利能力 / 动量 / EPS 修正 / 财务稳健）："
      f"{_weights_zh()}。成长期看重增速、成熟期看重估值与赚钱能力；金融股不做阶段标注，各维度等权（它们没有财务稳健维度，见该节）。",
      "Revenue growth leads and operating cash flow follows: revenue up ≥ 15% year over year with a 3-year CAGR "
      "≥ 10% (year over year only with under 3 years of history) is high growth — growth with positive operating "
      "cash flow, introduction otherwise. Revenue down ≥ 5% is shake-out with positive operating cash flow, "
      "contraction otherwise. Everything else is mature with positive operating cash flow, shake-out otherwise. "
      "A stage that was just crossed is kept for 2 extra points of growth to avoid flip-flopping. The stage sets the "
      "weights of the six dimensions in the composite (valuation / growth / profitability / momentum / EPS "
      f"revisions / financial health): {_weights_en()}. Growth stages lean on growth, mature stages on valuation and profitability; "
      "financials are not labeled and use equal weights (they have no financial-health dimension; see that section).")),
    (("A 股与港股", "China A-shares and Hong Kong"),
     ("规则与美股完全相同，只是比较样本与数据不同：A 股和总市值前 1800 只 A 股（不含 ST）比，港股和港股通标的及总市值 20 亿港元以上的港股比；"
      "行业按 GICS 11 个一级行业归类。报表为累计口径（一季、半年、三季、年报），换算成单季后计算最近 12 个月。"
      "A 股的分析师预期没有 EBITDA / EBIT，港股的分析师预期没有营收、EBITDA / EBIT，相应的前瞻指标不显示；"
      "银行、券商、保险不计算企业价值、毛利率、EBIT / EBITDA 类指标。港股财务数据与预期统一折成港元（股价币种），页面写明汇率。"
      "EPS 修正用自有的每日一致预期记录，积累满 30 天后启用。护城河评估暂只覆盖美股。",
      "Rules are identical to US stocks; only the peer sample and data differ. A-shares are compared with the 1,800 "
      "largest A-shares by market cap (excluding ST names); Hong Kong stocks with Stock Connect constituents plus "
      "stocks above HK$2 billion in market cap. Industries are mapped to the 11 GICS sectors. Statements are "
      "year-to-date cumulative and are converted to quarters before computing trailing 12 months. A-share consensus "
      "has no EBITDA / EBIT and Hong Kong consensus has no revenue, EBITDA or EBIT, so those forward metrics are not "
      "shown; banks, brokers and insurers skip enterprise-value, gross-margin and EBIT / EBITDA metrics. Hong Kong "
      "financials and estimates are converted to HKD (the price currency) and the rate is shown. EPS revisions use "
      "our own daily consensus records and start after 30 days. Moat assessments currently cover US stocks only.")),
    (("更新时间", "Updates"),
     ("美股、A 股、港股各自在收盘后重新计算；财报类数据在公司披露新财报后更新。页面上标注了行情日期、财报期与一致预期更新日。",
      "Recomputed after each market's close (US, A-shares, Hong Kong); statement data refreshes after new filings. "
      "Pages show the price date, fiscal period and consensus update date.")),
]


def build_methodology(lang: tx.Lang) -> MethodologyOut:
    """按规则常量生成方法说明（zh / en）。"""
    i = 0 if lang == "zh" else 1
    return MethodologyOut(
        methodology_version=METHODOLOGY_VERSION,
        sections=[{"title": t[i], "body": b[i]} for t, b in _SECTIONS],
        grade_bands=[GradeBand(grade=g, min_percentile=lo) for lo, g in BANDS],
        dimensions=[
            MethodologyDimension(
                key=dim, name=tx.dimension_name(dim, lang), description=tx.dimension_desc(dim, lang),
                metrics=[MethodologyMetric(key=k, name=d.name_zh if i == 0 else d.name_en,
                                           group=d.group if i == 0 else d.group_en, direction=d.direction,
                                           description=d.desc_zh if i == 0 else d.desc_en)
                         for k, d in METRICS.items() if d.dimension == dim])
            for dim in DIMENSIONS
        ],
        disclaimer=tx.DISCLAIMER[lang],
    )
