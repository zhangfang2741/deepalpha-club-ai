"""五维打分——纯函数，输入原始数据，输出 DimensionScore。

不做网络请求，便于单测。抓取在 fetchers.py，编排在 calculator.py。
"""
from typing import Optional

from app.schemas.institutional_signals import DimensionScore, SignalItem
from app.services.institutional_signals.constants import (
    BUY_RATIO_MAJORITY,
    DIMENSION_META,
    GAP_PCT,
    MIN_ANALYST_COUNT,
    RELVOL_ELEVATED,
    RELVOL_MILD,
    RELVOL_QUIET,
    RELVOL_STRONG,
    TP_MILD_PCT,
    TP_STRONG_PCT,
    VOLUME_LOOKBACK,
)


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, round(x, 1)))


def _meta(key: str) -> tuple[str, str]:
    return DIMENSION_META[key]


def unavailable_dimension(key: str, reason: str) -> DimensionScore:
    """尚未实现或数据缺失的维度占位（综合分计算时按权重剔除）。"""
    label, question = _meta(key)
    return DimensionScore(
        key=key,
        label=label,
        question=question,
        score=50.0,
        status="unavailable",
        signals=[SignalItem(key=f"{key}_pending", label="待接入", direction="flat", hit=False, detail=reason)],
    )


# ── Participation 参与度 ────────────────────────────────────────────────────

def compute_participation(prices: list[dict]) -> DimensionScore:
    """基于日线计算相对成交量、跳空、突破。

    prices：按日期升序的 list，每条含 date/open/high/low/close/volume。
    """
    label, question = _meta("participation")
    signals: list[SignalItem] = []

    if len(prices) < VOLUME_LOOKBACK + 1:
        return DimensionScore(
            key="participation", label=label, question=question,
            score=50.0, status="partial",
            signals=[SignalItem(key="insufficient_history", label="历史数据不足",
                                direction="flat", hit=False,
                                detail=f"需至少 {VOLUME_LOOKBACK + 1} 个交易日")],
        )

    last = prices[-1]
    prev = prices[-2]
    window = prices[-(VOLUME_LOOKBACK + 1):-1]  # 不含当日的前 20 日

    avg_vol = sum(p["volume"] for p in window) / len(window)
    rel_vol = last["volume"] / avg_vol if avg_vol else 0.0
    gap_pct = (last["open"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0.0
    window_high = max(p["high"] for p in window)
    window_low = min(p["low"] for p in window)
    breakout = last["close"] > window_high
    breakdown = last["close"] < window_low

    score = 50.0

    # 相对成交量
    if rel_vol >= RELVOL_STRONG:
        delta, rv_dir, rv_hit = 25, "up", True
    elif rel_vol >= RELVOL_ELEVATED:
        delta, rv_dir, rv_hit = 15, "up", True
    elif rel_vol >= RELVOL_MILD:
        delta, rv_dir, rv_hit = 8, "up", False
    elif rel_vol < RELVOL_QUIET:
        delta, rv_dir, rv_hit = -10, "down", False
    else:
        delta, rv_dir, rv_hit = 0, "flat", False
    score += delta
    signals.append(SignalItem(key="relative_volume", label="相对成交量",
                              value=f"{rel_vol:.1f}x", direction=rv_dir, hit=rv_hit,
                              detail="当日成交量 / 20 日均量"))

    # 跳空
    if gap_pct >= GAP_PCT:
        delta, g_dir, g_hit = 10, "up", True
    elif gap_pct <= -GAP_PCT:
        delta, g_dir, g_hit = -10, "down", True
    else:
        delta, g_dir, g_hit = 0, "flat", False
    score += delta
    signals.append(SignalItem(key="price_gap", label="跳空幅度",
                              value=f"{gap_pct:+.1f}%", direction=g_dir, hit=g_hit,
                              detail="当日开盘 vs 昨收"))

    # 突破 / 跌破
    if breakout:
        delta, b_dir, b_hit, b_detail = 15, "up", True, "收盘创 20 日新高"
    elif breakdown:
        delta, b_dir, b_hit, b_detail = -15, "down", True, "收盘创 20 日新低"
    else:
        delta, b_dir, b_hit, b_detail = 0, "flat", False, "20 日区间内"
    score += delta
    signals.append(SignalItem(key="breakout", label="价格突破",
                              value=b_detail, direction=b_dir, hit=b_hit))

    return DimensionScore(key="participation", label=label, question=question,
                          score=_clamp(score), status="ok", signals=signals)


# ── Expectation 预期 ────────────────────────────────────────────────────────

def _buy_ratio(row: dict) -> Optional[float]:
    sb = row.get("analystRatingsStrongBuy") or row.get("strongBuy") or 0
    b = row.get("analystRatingsBuy") or row.get("buy") or 0
    h = row.get("analystRatingsHold") or row.get("hold") or 0
    s = row.get("analystRatingsSell") or row.get("sell") or 0
    ss = row.get("analystRatingsStrongSell") or row.get("strongSell") or 0
    total = sb + b + h + s + ss
    if total <= 0:
        return None
    return (sb + b) / total


def compute_expectation(
    pt_summary: Optional[dict],
    grades_hist: list[dict],
) -> DimensionScore:
    """目标价修正（price-target-summary）+ 评级趋势（grades-historical）。

    EPS/Revenue 修正需每日快照（Phase 4），此处先标 partial。
    """
    label, question = _meta("expectation")
    signals: list[SignalItem] = []
    score = 50.0
    has_data = False

    # 目标价：月 vs 季 vs 年
    if pt_summary:
        m = pt_summary.get("lastMonthAvgPriceTarget") or 0
        q = pt_summary.get("lastQuarterAvgPriceTarget") or 0
        count = pt_summary.get("lastMonthCount") or 0
        if m and q and count >= MIN_ANALYST_COUNT:
            has_data = True
            mom = (m - q) / q * 100 if q else 0.0
            if mom >= TP_STRONG_PCT:
                delta, tp_dir, tp_hit = 20, "up", True
            elif mom >= TP_MILD_PCT:
                delta, tp_dir, tp_hit = 12, "up", True
            elif mom <= -TP_MILD_PCT:
                delta, tp_dir, tp_hit = -15, "down", True
            else:
                delta, tp_dir, tp_hit = 0, "flat", False
            score += delta
            signals.append(SignalItem(key="target_price", label="目标价修正",
                                      value=f"{mom:+.1f}%", direction=tp_dir, hit=tp_hit,
                                      detail=f"近月均值 vs 近季均值（{count} 家）"))

    # 评级趋势：最近月 vs 上一有效月的买入占比
    latest_ratio = prev_ratio = None
    for row in sorted(grades_hist, key=lambda r: str(r.get("date", "")), reverse=True):
        r = _buy_ratio(row)
        if r is None:
            continue
        if latest_ratio is None:
            latest_ratio = r
        elif prev_ratio is None:
            prev_ratio = r
            break
    if latest_ratio is not None:
        has_data = True
        if prev_ratio is not None and latest_ratio > prev_ratio + 0.02:
            delta, rt_dir, rt_hit = 15, "up", True
        elif prev_ratio is not None and latest_ratio < prev_ratio - 0.02:
            delta, rt_dir, rt_hit = -15, "down", True
        elif latest_ratio >= BUY_RATIO_MAJORITY:
            delta, rt_dir, rt_hit = 8, "up", False
        else:
            delta, rt_dir, rt_hit = 0, "flat", False
        score += delta
        signals.append(SignalItem(key="analyst_rating", label="评级共识",
                                  value=f"买入占比 {latest_ratio * 100:.0f}%",
                                  direction=rt_dir, hit=rt_hit,
                                  detail="强买+买入 / 总评级家数"))

    # EPS / Revenue 修正——待快照持久化（Phase 4）
    for key, lab in (("eps_revision", "EPS 修正"), ("revenue_revision", "营收修正")):
        signals.append(SignalItem(key=key, label=lab, direction="flat", hit=False,
                                  detail="待每日快照持久化（Phase 4）"))

    status = "ok" if has_data else "partial"
    return DimensionScore(key="expectation", label=label, question=question,
                          score=_clamp(score), status=status, signals=signals)
