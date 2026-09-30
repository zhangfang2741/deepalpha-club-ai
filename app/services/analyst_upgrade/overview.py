"""个股分析师评级概览：把 FMP 原始响应整理成缠论 App「分析师评级」Tab 的结构。纯函数，无 IO。

- 评级分布只用 grades-historical（不混用 grades-consensus：两者口径不同，NVDA 同日 63 vs 79 家）。
- 评级标签是分析师原话，只做引述（保留原文 + 中文对照）；我们生成的文案保持中性，不写「上涨空间」等。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from app.schemas.analyst_upgrade import (
    AnalystOverviewOut,
    EarningsQuarter,
    EarningsSection,
    GradeChange,
    NextEarnings,
    PriceTargetSection,
    RatingCounts,
    RatingSection,
)

Lang = Literal["zh", "en"]

ACTION_LABELS = {
    "upgrade": ("上调", "Upgrade"), "downgrade": ("下调", "Downgrade"), "maintain": ("维持", "Maintain"),
    "init": ("首次覆盖", "Initiate"), "initialise": ("首次覆盖", "Initiate"), "reiterated": ("重申", "Reiterate"),
}
GRADE_LABELS_ZH = {
    "strong buy": "强力买入", "buy": "买入", "outperform": "跑赢大盘", "market outperform": "跑赢大盘",
    "sector outperform": "跑赢板块", "overweight": "增持", "accumulate": "增持", "positive": "正面",
    "hold": "持有", "neutral": "中性", "equal weight": "同等权重", "equal-weight": "同等权重",
    "market perform": "与大盘持平", "sector perform": "与板块持平", "sector weight": "板块权重", "perform": "持平",
    "in-line": "持平", "peer perform": "与同业持平", "underperform": "跑输大盘", "underweight": "减持",
    "reduce": "减持", "negative": "负面", "sell": "卖出", "strong sell": "强力卖出",
}
NOTE = {
    "zh": "本页内容均为分析师给出的评级、目标价与预期，按原样引述，不代表本 App 的观点，不构成投资建议。",
    "en": "Everything on this page is quoted from analysts' ratings, price targets and estimates. It does not "
          "represent this app's view and is not investment advice.",
}


def _i(lang: Lang, zh: str, en: str) -> str:
    return zh if lang == "zh" else en


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def grade_label(grade: str | None, lang: Lang) -> str | None:
    """评级原文 → 展示标签（中文对照；未知的保留原文）。"""
    if grade is None:
        return None
    if lang == "en":
        return grade
    return GRADE_LABELS_ZH.get(grade.strip().lower(), grade)


def build_ratings(hist: list | None, lang: Lang) -> RatingSection | None:
    """月度评级分布（旧 → 新）+ 近 3 个月买入及以上人数变化。"""
    rows = sorted([h for h in hist or [] if isinstance(h, dict) and h.get("date")], key=lambda h: h["date"])[-12:]
    if not rows:
        return None
    counts = []
    for h in rows:
        vals = [int(h.get(k) or 0) for k in ("analystRatingsStrongBuy", "analystRatingsBuy", "analystRatingsHold",
                                               "analystRatingsSell", "analystRatingsStrongSell")]
        counts.append(RatingCounts(date=str(h["date"])[:10], strong_buy=vals[0], buy=vals[1], hold=vals[2],
                                   sell=vals[3], strong_sell=vals[4], total=sum(vals)))
    cur = counts[-1]
    change = None
    if len(counts) >= 4:
        old = counts[-4]
        a, b = old.strong_buy + old.buy, cur.strong_buy + cur.buy
        if a == b:
            change = _i(lang, f"近 3 个月：给出「买入」及以上评级的分析师保持 {b} 位",
                        f"Last 3 months: analysts at Buy or above unchanged at {b}")
        else:
            verb_zh, verb_en = ("增至", "rose") if b > a else ("减至", "fell")
            change = _i(lang, f"近 3 个月：给出「买入」及以上评级的分析师由 {a} 位{verb_zh} {b} 位",
                        f"Last 3 months: analysts at Buy or above {verb_en} from {a} to {b}")
    return RatingSection(current=cur, history=counts, change_text=change)


def build_price_target(ptc: list | None, pts: list | None, quote: list | None, lang: Lang) -> PriceTargetSection | None:
    """目标价与现价；较现价的百分比只是算术差。"""
    c = ptc[0] if isinstance(ptc, list) and ptc else None
    s = pts[0] if isinstance(pts, list) and pts else {}
    price = _num(quote[0].get("price")) if isinstance(quote, list) and quote else None
    if c is None:
        return None
    median = _num(c.get("targetMedian"))
    pct = (median / price - 1) * 100 if (median and price) else None
    text = None
    if pct is not None:
        text = _i(lang, f"目标价中位数较现价 {pct:+.1f}%", f"Median target is {pct:+.1f}% vs the current price")
    return PriceTargetSection(
        price=price, high=_num(c.get("targetHigh")), low=_num(c.get("targetLow")), median=median,
        consensus=_num(c.get("targetConsensus")), vs_price_pct=round(pct, 1) if pct is not None else None,
        vs_price_text=text, last_month_count=s.get("lastMonthCount"), last_quarter_count=s.get("lastQuarterCount"),
        last_year_count=s.get("lastYearCount"),
    )


def build_earnings(earnings: list | None, today: date) -> EarningsSection | None:
    """近 4 个已披露季度的 EPS 实际 vs 预期，以及下次披露。"""
    rows = [e for e in earnings or [] if isinstance(e, dict) and e.get("date")]
    if not rows:
        return None
    done = sorted([e for e in rows if e.get("epsActual") is not None], key=lambda e: e["date"])[-4:]
    quarters = []
    for e in done:
        act, est = float(e["epsActual"]), _num(e.get("epsEstimated"))
        surprise = (act - est) / abs(est) * 100 if est else None
        quarters.append(EarningsQuarter(date=str(e["date"])[:10], eps_actual=act, eps_estimated=est,
                                        surprise_pct=round(surprise, 1) if surprise is not None else None))
    upcoming = sorted([e for e in rows if e.get("epsActual") is None and str(e["date"]) >= today.isoformat()],
                      key=lambda e: e["date"])
    nxt = None
    if upcoming:
        u = upcoming[0]
        nxt = NextEarnings(date=str(u["date"])[:10], eps_estimated=_num(u.get("epsEstimated")),
                           revenue_estimated=_num(u.get("revenueEstimated")))
    return EarningsSection(quarters=quarters, next=nxt)


def build_recent_grades(grades: list | None, lang: Lang, limit: int = 10) -> list[GradeChange]:
    """最近的机构评级变动（新 → 旧）。"""
    rows = sorted([g for g in grades or [] if isinstance(g, dict) and g.get("date") and g.get("newGrade")],
                  key=lambda g: g["date"], reverse=True)[:limit]
    out = []
    for g in rows:
        action = str(g.get("action") or "").lower()
        zh, en = ACTION_LABELS.get(action, (action, action.title()))
        prev = g.get("previousGrade") or None
        out.append(GradeChange(
            date=str(g["date"])[:10], firm=str(g.get("gradingCompany") or ""), action=action,
            action_label=_i(lang, zh, en), previous_grade=prev, previous_grade_label=grade_label(prev, lang),
            new_grade=str(g["newGrade"]), new_grade_label=grade_label(str(g["newGrade"]), lang) or "",
        ))
    return out


def build_overview(symbol: str, lang: Lang, today: date, *, hist=None, ptc=None, pts=None, earnings=None,
                   grades=None, quote=None) -> AnalystOverviewOut:
    """组装完整概览；各区块独立，任一缺失不影响其他。"""
    ratings = build_ratings(hist, lang)
    target = build_price_target(ptc, pts, quote, lang)
    earn = build_earnings(earnings, today)
    recent = build_recent_grades(grades, lang)
    if not any([ratings, target, earn, recent]):
        return AnalystOverviewOut(symbol=symbol, status="insufficient_data", note=NOTE[lang],
                                  status_note=_i(lang, "暂无分析师数据", "No analyst data available"))
    return AnalystOverviewOut(symbol=symbol, status="ok", ratings=ratings, price_target=target, earnings=earn,
                              recent_grades=recent, note=NOTE[lang])


def unsupported(symbol: str, lang: Lang) -> AnalystOverviewOut:
    """非美股。"""
    return AnalystOverviewOut(symbol=symbol, status="unsupported_market", note=NOTE[lang],
                              status_note=_i(lang, "分析师评级暂只支持美股", "Analyst ratings currently cover US stocks only"))
