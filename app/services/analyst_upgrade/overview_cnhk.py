"""A 股 / 港股分析师评级概览（纯函数，无 IO）。与美股同一个响应结构，档位换成中文券商通行的五档。

- A 股：评级分布用 F10 的官方评级统计（近 6 个月内给出评级的机构，按东财统一五档；研报列表只收录部分研报，
  茅台实测列表里只有 14 家而统计是 43 家，所以分布不用列表重建）；F10 缺失时才退回用研报列表按机构去重计数。
  最近评级变动与目标价用逐篇研报（机构、发布日、本次 / 上次评级、目标价；近 6 个月 ≥ 3 家给出目标价才显示）。
- 港股：每家券商只有最新评级与目标价（无历史），只给当前分布、目标价、各券商最新评级列表。
- 评级原文只引述；档位归并见 quant_research/cnhk/ratings.py，未知评级不计入分布。
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, median

from app.schemas.analyst_upgrade import (
    AnalystOverviewOut,
    GradeChange,
    PriceTargetSection,
    RatingCounts,
    RatingSection,
)
from app.services.analyst_upgrade.overview import NOTE, Lang, _i
from app.services.quant_research.cnhk.etnet import EtnetForecast
from app.services.quant_research.cnhk.ratings import TIER_LABELS, tier

WINDOW_DAYS = 182
MIN_TARGETS = 3
_ACTIONS = {"upgrade": ("上调", "Upgrade"), "downgrade": ("下调", "Downgrade"), "maintain": ("维持", "Maintain"),
            "init": ("首次覆盖", "Initiate"), "latest": ("最新", "Latest")}


def _f(v) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def _counts(tiers: list[int], day: date) -> RatingCounts:
    c = [tiers.count(i) for i in range(5)]
    return RatingCounts(date=day.isoformat(), strong_buy=c[0], buy=c[1], hold=c[2], sell=c[3], strong_sell=c[4],
                        total=sum(c))


def _month_ends(today: date, n: int = 12) -> list[date]:
    """最近 n 个月的月末（最后一个是今天），旧 → 新。"""
    out = [today]
    d = today.replace(day=1) - timedelta(days=1)
    while len(out) < n:
        out.append(d)
        d = d.replace(day=1) - timedelta(days=1)
    return sorted(out)


def _change_text(counts: list[RatingCounts], lang: Lang) -> str | None:
    """近 3 个月「增持」及以上（前两档）家数的变化，中性描述。"""
    if len(counts) < 4:
        return None
    old, cur = counts[-4], counts[-1]
    a, b = old.strong_buy + old.buy, cur.strong_buy + cur.buy
    label = TIER_LABELS[lang][1]
    if a == b:
        return _i(lang, f"近 3 个月：给出「{label}」及以上评级的机构保持 {b} 家",
                  f"Last 3 months: institutions at {label} or above unchanged at {b}")
    verb_zh, verb_en = ("增至", "rose") if b > a else ("减至", "fell")
    return _i(lang, f"近 3 个月：给出「{label}」及以上评级的机构由 {a} 家{verb_zh} {b} 家",
              f"Last 3 months: institutions at {label} or above {verb_en} from {a} to {b}")


def _target_section(targets: list[float], dates: list[date], price: float | None, today: date,
                    lang: Lang) -> PriceTargetSection | None:
    if len(targets) < MIN_TARGETS:
        return None
    med = median(targets)
    pct = (med / price - 1) * 100 if price else None
    return PriceTargetSection(
        price=price, high=max(targets), low=min(targets), median=round(med, 2), consensus=round(mean(targets), 2),
        vs_price_pct=round(pct, 1) if pct is not None else None,
        vs_price_text=_i(lang, f"目标价中位数较现价 {pct:+.1f}%", f"Median target is {pct:+.1f}% vs the current price")
        if pct is not None else None,
        last_month_count=sum(1 for d in dates if (today - d).days <= 30),
        last_quarter_count=sum(1 for d in dates if (today - d).days <= 91),
        last_year_count=sum(1 for d in dates if (today - d).days <= 365),
    )


def _tier_label(name: str | None, lang: Lang) -> str | None:
    t = tier(name)
    if name is None:
        return None
    return name if lang == "zh" or t is None else TIER_LABELS["en"][t]


# ---------- A 股 ----------

def _report_date(r: dict) -> date | None:
    try:
        return date.fromisoformat(str(r.get("publishDate") or "")[:10])
    except ValueError:
        return None


def cn_rating_stats(f10: dict | None, today: date, lang: Lang) -> RatingSection | None:
    """F10 评级统计「6月内」→ 当前分布（买入 / 增持 / 中性 / 减持 / 卖出 家数）。"""
    row = next((r for r in (f10 or {}).get("pjtj") or [] if r.get("DATE_TYPE") == "6月内"), None)
    if row is None:
        return None
    c = [int(row.get(k) or 0) for k in ("RATING_BUY_NUM", "RATING_ADD_NUM", "RATING_NEUTRAL_NUM",
                                         "RATING_REDUCE_NUM", "RATING_SALE_NUM")]
    if not sum(c):
        return None
    cur = RatingCounts(date=today.isoformat(), strong_buy=c[0], buy=c[1], hold=c[2], sell=c[3], strong_sell=c[4],
                       total=sum(c))
    return RatingSection(current=cur, history=[cur], change_text=None, bucket_labels=TIER_LABELS[lang])


def build_cn_overview(symbol: str, lang: Lang, today: date, reports: list[dict], price: float | None,
                      f10: dict | None = None) -> AnalystOverviewOut:
    """A 股 F10 评级统计 + 研报列表 → 概览。"""
    rows = [(d, r) for r in reports if (d := _report_date(r)) is not None and r.get("orgSName")]
    rows.sort(key=lambda x: x[0], reverse=True)
    official = cn_rating_stats(f10, today, lang)
    if not rows and official is None:
        return _empty(symbol, lang)

    def snapshot(end: date) -> list[int]:
        seen: dict[str, int] = {}
        for d, r in rows:  # 新 → 旧：每家机构取窗口内最近一次
            if d > end or (end - d).days > WINDOW_DAYS or r["orgSName"] in seen:
                continue
            t = tier(r.get("emRatingName"))
            if t is not None:
                seen[r["orgSName"]] = t
        return list(seen.values())

    ratings = official
    if ratings is None and rows:  # 没有官方统计：按研报列表逐月重建（每家机构取近 6 个月最近一次）
        history = [h for h in (_counts(snapshot(e), e) for e in _month_ends(today)) if h.total > 0]
        ratings = RatingSection(current=history[-1], history=history, change_text=_change_text(history, lang),
                                bucket_labels=TIER_LABELS[lang]) if history else None

    latest_target: dict[str, tuple[date, float]] = {}
    for d, r in rows:
        t = _f(r.get("indvAimPriceT"))
        if t is not None and (today - d).days <= WINDOW_DAYS and r["orgSName"] not in latest_target:
            latest_target[r["orgSName"]] = (d, t)
    target = _target_section([t for _, t in latest_target.values()], [d for d, _ in latest_target.values()],
                             price, today, lang)

    recent = []
    for i, (d, r) in enumerate(rows[:10]):
        new = r.get("emRatingName") or r.get("sRatingName")
        if not new:
            continue
        prev_em = r.get("lastEmRatingName") or None
        # 上次评级原文：同一机构更早的一篇研报；找不到就用东财统一后的上次评级
        older = next((o for _, o in rows[i + 1:] if o["orgSName"] == r["orgSName"]), None)
        prev_raw = (older.get("sRatingName") or older.get("emRatingName")) if older else prev_em
        action = _cn_action(new, prev_em)
        zh, en = _ACTIONS[action]
        raw_new = r.get("sRatingName") or new
        if lang == "zh":  # 中文引述券商原文（如「强烈推荐」）
            new_label, prev_label = raw_new, prev_raw
        else:             # 英文用东财统一后的五档译名
            new_label = _tier_label(new, "en") or raw_new
            prev_label = _tier_label(prev_em or prev_raw, "en")
        recent.append(GradeChange(
            date=d.isoformat(), firm=str(r["orgSName"]), action=action, action_label=_i(lang, zh, en),
            previous_grade=prev_raw, previous_grade_label=prev_label, new_grade=raw_new, new_grade_label=new_label,
            price_target=_f(r.get("indvAimPriceT")),
            report_title=(r.get("title") or None), report_url=_report_url(r.get("infoCode")), report_kind="report",
        ))
    if ratings is None and target is None and not recent:
        return _empty(symbol, lang)
    return AnalystOverviewOut(symbol=symbol, status="ok", ratings=ratings, price_target=target, earnings=None,
                              recent_grades=recent, note=NOTE[lang])


def _report_url(info_code: str | None) -> str | None:
    """东财研报编号 → 研报原文 PDF 直链（App 下载后在本地缓存、应用内阅读）（只接受字母数字编号，避免拼出奇怪的链接）。"""
    if not info_code or not str(info_code).isalnum():
        return None
    return f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


def _cn_action(new: str | None, prev: str | None) -> str:
    """东财统一后的本次 / 上次评级 → 首次覆盖 / 上调 / 下调 / 维持。"""
    if not prev:
        return "init"
    a, b = tier(prev), tier(new)
    if a is None or b is None or a == b:
        return "maintain"
    return "upgrade" if b < a else "downgrade"


# ---------- 港股 ----------

def build_hk_overview(symbol: str, lang: Lang, today: date, fc: EtnetForecast | None,
                      price: float | None) -> AnalystOverviewOut:
    """经济通各券商最新评级 / 目标价 → 概览（无历史趋势）。"""
    if fc is None:
        return _empty(symbol, lang)
    rated = [r for r in fc.rows if r.rating and r.updated is not None]
    if not rated:
        return _empty(symbol, lang)
    fy1 = min(r.fiscal_year for r in rated)
    rows = sorted((r for r in rated if r.fiscal_year == fy1), key=lambda r: r.updated or today, reverse=True)
    fresh = [r for r in rows if (today - r.updated).days <= WINDOW_DAYS]  # type: ignore[operator]
    tiers = [t for r in fresh if (t := tier(r.rating)) is not None]
    cur = _counts(tiers, today)
    ratings = RatingSection(current=cur, history=[cur], change_text=None, bucket_labels=TIER_LABELS[lang]) if tiers else None
    with_target = [r for r in fresh if r.target_hkd]
    target = _target_section([r.target_hkd for r in with_target], [r.updated for r in with_target],  # type: ignore[misc]
                             price, today, lang)
    zh, en = _ACTIONS["latest"]
    recent = [GradeChange(date=r.updated.isoformat(), firm=r.firm, action="latest", action_label=_i(lang, zh, en),  # type: ignore[union-attr]
                          new_grade=r.rating or "", new_grade_label=_tier_label(r.rating, lang) or (r.rating or ""),
                          price_target=r.target_hkd)
              for r in rows[:10]]
    return AnalystOverviewOut(symbol=symbol, status="ok", ratings=ratings, price_target=target, earnings=None,
                              recent_grades=recent, recent_grades_title=_i(lang, "各券商最新评级", "Latest rating by broker"),
                              note=NOTE[lang])


def _empty(symbol: str, lang: Lang) -> AnalystOverviewOut:
    return AnalystOverviewOut(symbol=symbol, status="insufficient_data", note=NOTE[lang],
                              status_note=_i(lang, "暂无分析师数据", "No analyst data available"))
