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
from app.services.quant_research.scoring import CAP_CEILING, MIN_SAMPLE

_SECTIONS: list[tuple[tuple[str, str], tuple[str, str]]] = [
    (("和谁比", "Who it is compared with"),
     ("标普500与纳斯达克100的并集按 GICS 11 个板块分组，每项指标只和同板块公司比较。"
      "不在这两个指数并集内的美股，按它所在板块当天的分布定位。结果只表示在同行中的相对位置，"
      "指标详情里同时给出本股数值与板块中位数。",
      "The union of the S&P 500 and Nasdaq-100 is grouped into the 11 GICS sectors and every metric is "
      "compared only within the sector. US stocks outside this union are placed against that day's sector "
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
     (f"综合分 = 可用维度分的等权平均；再看综合分在标普500与纳斯达克100并集中的百分位，按同一把尺子定等级。"
      f"任一维度为 F 时，综合等级最高为 {CAP_CEILING}；覆盖的分析师少于 {MIN_ANALYSTS} 位时不给综合等级。",
      f"The composite score is the equal-weighted average of available dimension scores; its percentile across the "
      f"whole S&P 500 + Nasdaq-100 union sets the grade on the same scale. If any dimension is F, the composite is capped at "
      f"{CAP_CEILING}; with fewer than {MIN_ANALYSTS} covering analysts there is no composite grade.")),
    (("EPS 修正", "EPS revisions"),
     ("每天保存一次分析师一致预期，比较当前值与 30 / 90 天前的值；亏损收窄算上修。"
      "历史不足 30 天时该维度显示「积累中」，综合等级基于其余维度。本维度用一致预期均值的变化，"
      "而不是上调 / 下调的分析师人数。",
      "Analyst consensus is saved daily and compared with its value 30 and 90 days earlier; a narrowing loss counts "
      "as an upward revision. With under 30 days of history the dimension shows as building, and the composite uses "
      "the other dimensions. The change in the consensus mean is used rather than counts of raising or cutting "
      "analysts.")),
    (("公司阶段", "Company stage"),
     ("按最近 12 个月经营 / 投资 / 筹资现金流的正负划分：初创（− − +）、成长（+ − +）、成熟（+ − −）、"
      "收缩（− + ±），其余为调整期。只做标注，不影响等级；金融股不做阶段标注。",
      "Stages follow the signs of trailing operating / investing / financing cash flows: introduction (− − +), "
      "growth (+ − +), mature (+ − −), contraction (− + ±), otherwise shake-out. Stages are labels only and do not "
      "change grades; financials are not labeled.")),
    (("更新时间", "Updates"),
     ("每个美股交易日收盘后重新计算；财报类数据在公司披露新财报后更新。页面上标注了行情日期、财报期与一致预期更新日。",
      "Recomputed after every US trading day; statement data refreshes after new filings. Pages show the price date, "
      "fiscal period and consensus update date.")),
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
