"""五维打分——纯函数，输入原始数据，输出 DimensionScore。

不做网络请求，便于单测。抓取在 fetchers.py，编排在 calculator.py。
"""
import datetime
from typing import Optional

from app.schemas.institutional_signals import DimensionScore, SignalExplanation, SignalItem

from app.services.institutional_signals.constants import (
    BUY_RATIO_MAJORITY,
    CALL_VOL_OI_FRESH,
    DIMENSION_META,
    EARNINGS_LOOKBACK_QUARTERS,
    EARNINGS_WINDOW_DAYS,
    GAP_PCT,
    INSIDER_ACCUM_RATIO,
    INSIDER_DISTRIB_RATIO,
    INSIDER_DISTRIB_SALES,
    INSIDER_LOOKBACK_QUARTERS,
    IV_ELEVATED,
    IV_MILD,
    MIN_ANALYST_COUNT,
    PCR_CALL_HEAVY,
    PCR_MILD_CALL,
    PCR_PUT_HEAVY,
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

    if not prices:
        return unavailable_dimension("participation", "价格数据不可用")
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
                              detail="当日成交量 / 20 日均量",
                              explain=SignalExplanation(
                                  inputs=[f"当日成交量 = {last['volume']:,.0f}",
                                          f"前 20 日均量 = {avg_vol:,.0f}"],
                                  formula=f"相对成交量 = {last['volume']:,.0f} ÷ {avg_vol:,.0f} = {rel_vol:.2f}x",
                                  thresholds="≥2.0 显著放量(+25) · ≥1.5 放量(+15) · ≥1.2 温和(+8) · <0.8 缩量(−10)",
                                  conclusion=f"{rel_vol:.2f}x → {'放量，命中 ↑' if rv_hit else '未达放量阈值'}（{delta:+d} 分）",
                                  source="FMP historical-price-eod")))

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
                              detail="当日开盘 vs 昨收",
                              explain=SignalExplanation(
                                  inputs=[f"当日开盘价 = ${last['open']:.2f}", f"昨日收盘价 = ${prev['close']:.2f}"],
                                  formula=f"跳空 = (${last['open']:.2f} − ${prev['close']:.2f}) ÷ ${prev['close']:.2f} × 100 = {gap_pct:+.1f}%",
                                  thresholds="≥ +2% 高开(+10) · ≤ −2% 低开(−10) · 其余持平",
                                  conclusion=f"{gap_pct:+.1f}% → {'跳空命中' if g_hit else '无显著跳空'}（{delta:+d} 分）",
                                  source="FMP historical-price-eod")))

    # 突破 / 跌破
    if breakout:
        delta, b_dir, b_hit, b_detail = 15, "up", True, "收盘创 20 日新高"
    elif breakdown:
        delta, b_dir, b_hit, b_detail = -15, "down", True, "收盘创 20 日新低"
    else:
        delta, b_dir, b_hit, b_detail = 0, "flat", False, "20 日区间内"
    score += delta
    signals.append(SignalItem(key="breakout", label="价格突破",
                              value=b_detail, direction=b_dir, hit=b_hit,
                              explain=SignalExplanation(
                                  inputs=[f"当日收盘价 = ${last['close']:.2f}",
                                          f"前 20 日最高 = ${window_high:.2f}",
                                          f"前 20 日最低 = ${window_low:.2f}"],
                                  formula=f"${last['close']:.2f} vs 区间 [${window_low:.2f}, ${window_high:.2f}]",
                                  thresholds="收盘 > 20 日高 → 突破(+15) · 收盘 < 20 日低 → 跌破(−15)",
                                  conclusion=f"{b_detail}（{delta:+d} 分）",
                                  source="FMP historical-price-eod")))

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
    eps_revision_pct: Optional[float] = None,
    revenue_revision_pct: Optional[float] = None,
) -> DimensionScore:
    """目标价修正（price-target-summary）+ 评级趋势（grades-historical）。

    EPS/Revenue 修正来自每日快照库：有历史时传入 *_revision_pct（近 90 天一致预期变化），
    无历史时为 None → 仍标为待接入。
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
            _tp_verdict = ("强上调" if mom >= TP_STRONG_PCT else "上调" if mom >= TP_MILD_PCT
                           else "下调" if mom <= -TP_MILD_PCT else "持平")
            signals.append(SignalItem(key="target_price", label="目标价修正",
                                      value=f"{mom:+.1f}%", direction=tp_dir, hit=tp_hit,
                                      detail=f"近月均值 vs 近季均值（{count} 家）",
                                      explain=SignalExplanation(
                                          inputs=[f"近 1 月分析师目标价均值 = ${m:.2f}（{count} 家覆盖）",
                                                  f"近 1 季分析师目标价均值 = ${q:.2f}"],
                                          formula=f"环比 = (${m:.2f} − ${q:.2f}) ÷ ${q:.2f} × 100 = {mom:+.1f}%",
                                          thresholds=f"≥ +{TP_STRONG_PCT:.0f}% 强上调(+20) · ≥ +{TP_MILD_PCT:.0f}% 上调(+12) · ≤ −{TP_MILD_PCT:.0f}% 下调(−15)",
                                          conclusion=f"{mom:+.1f}% → 判定「{_tp_verdict}」，{'命中 ↑' if tp_hit and tp_dir == 'up' else '命中 ↓' if tp_hit else '未命中'}（{delta:+d} 分）",
                                          source="FMP price-target-summary")))

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
        _prev_txt = f"上一月买入占比 = {prev_ratio * 100:.0f}%" if prev_ratio is not None else "无上一月可比数据"
        if prev_ratio is not None and latest_ratio > prev_ratio + 0.02:
            _rt_concl = f"环比 +{(latest_ratio - prev_ratio) * 100:.0f}pt（>2pt）→ 共识转多，命中 ↑（+15 分）"
        elif prev_ratio is not None and latest_ratio < prev_ratio - 0.02:
            _rt_concl = f"环比 {(latest_ratio - prev_ratio) * 100:.0f}pt（<−2pt）→ 共识转空，命中 ↓（−15 分）"
        elif latest_ratio >= BUY_RATIO_MAJORITY:
            _rt_concl = f"买入占比 ≥ {BUY_RATIO_MAJORITY * 100:.0f}% → 偏多（+8 分，未作为组合命中）"
        else:
            _rt_concl = "无显著变化（0 分）"
        signals.append(SignalItem(key="analyst_rating", label="评级共识",
                                  value=f"买入占比 {latest_ratio * 100:.0f}%",
                                  direction=rt_dir, hit=rt_hit,
                                  detail="强买+买入 / 总评级家数",
                                  explain=SignalExplanation(
                                      inputs=[f"最近月买入占比 = {latest_ratio * 100:.0f}%", _prev_txt],
                                      formula="买入占比 = (强买 + 买入) ÷ 总评级家数",
                                      thresholds="环比 +2pt 转多(+15) · 环比 −2pt 转空(−15) · 占比 ≥ 60% 偏多(+8)",
                                      conclusion=_rt_concl,
                                      source="FMP grades-historical")))

    # EPS / Revenue 修正——来自每日快照库（近 90 天一致预期变化）
    for key, lab, pct in (
        ("eps_revision", "EPS 修正", eps_revision_pct),
        ("revenue_revision", "营收修正", revenue_revision_pct),
    ):
        if pct is None:
            signals.append(SignalItem(key=key, label=lab, direction="flat", hit=False,
                                      detail="快照历史不足（需累积 ≥30 天）"))
            continue
        has_data = True
        if pct >= 1.0:
            delta, rv_dir, rv_hit = 12, "up", True
        elif pct <= -1.0:
            delta, rv_dir, rv_hit = -12, "down", True
        else:
            delta, rv_dir, rv_hit = 0, "flat", False
        score += delta
        signals.append(SignalItem(key=key, label=lab, value=f"{pct:+.1f}%",
                                  direction=rv_dir, hit=rv_hit, detail="近 90 天一致预期变化",
                                  explain=SignalExplanation(
                                      inputs=[f"当前分析师一致{lab.replace('修正', '')}预期",
                                              "对比约 90 天前的快照记录"],
                                      formula=f"修正 = (当前 − 90天前) ÷ 90天前 × 100 = {pct:+.1f}%",
                                      thresholds="≥ +1% 上修(+12) · ≤ −1% 下修(−12)",
                                      conclusion=f"{pct:+.1f}% → {'上修，命中 ↑' if rv_hit and rv_dir == 'up' else '下修，命中 ↓' if rv_hit else '无显著修正'}（{delta:+d} 分）",
                                      source="FMP analyst-estimates + 每日快照库")))

    if not has_data:
        return unavailable_dimension("expectation", "无目标价/评级数据")
    return DimensionScore(key="expectation", label=label, question=question,
                          score=_clamp(score), status="ok", signals=signals)


# ── Positioning 仓位（期权快照）─────────────────────────────────────────────

def compute_positioning(
    metrics: Optional[dict],
    iv_rank_value: Optional[float] = None,
    oi_change_pct: Optional[float] = None,
) -> DimensionScore:
    """基于 yfinance 期权快照的 Put/Call 比、Call 量/仓比 + 快照库衍生的 IV Rank / OI 变化。

    metrics 字段（由 fetchers 聚合近月合约得到）：
        call_vol / put_vol / call_oi / put_oi（整型求和）、atm_iv（年化小数）。
    有快照历史时传入 iv_rank_value（0–100）与 oi_change_pct（Call OI 近 5 日变化）；
    无历史时为 None → IV 回退到「水平」口径、不显示 OI 变化。
    """
    label, question = _meta("positioning")

    if not metrics:
        return unavailable_dimension("positioning", "期权数据不可用（yfinance 无期权链或拉取失败）")

    call_vol = metrics.get("call_vol") or 0
    put_vol = metrics.get("put_vol") or 0
    call_oi = metrics.get("call_oi") or 0
    put_oi = metrics.get("put_oi") or 0
    atm_iv = metrics.get("atm_iv") or 0.0

    if call_vol + put_vol == 0:
        return DimensionScore(
            key="positioning", label=label, question=question, score=50.0, status="partial",
            signals=[SignalItem(key="no_option_volume", label="当日期权无成交",
                                direction="flat", hit=False, detail="非交易时段或流动性极低")],
        )

    pcr_vol = put_vol / call_vol if call_vol else 99.0
    pcr_oi = put_oi / call_oi if call_oi else 99.0
    call_vol_oi = call_vol / call_oi if call_oi else 0.0

    signals: list[SignalItem] = []
    score = 50.0

    # Call 资金流：看涨下注（Put/Call 低 + 当日 Call 量/仓高）
    if pcr_vol <= PCR_CALL_HEAVY and call_vol_oi >= CALL_VOL_OI_FRESH:
        delta, cf_dir, cf_hit = 20, "up", True
    elif pcr_vol <= PCR_MILD_CALL:
        delta, cf_dir, cf_hit = 8, "up", False
    else:
        delta, cf_dir, cf_hit = 0, "flat", False
    score += delta
    signals.append(SignalItem(key="call_flow", label="Call 资金流",
                              value=f"PCR {pcr_vol:.2f} · 量/仓 {call_vol_oi:.2f}",
                              direction=cf_dir, hit=cf_hit,
                              detail="Put/Call 成交量比 + Call 当日量/未平仓量",
                              explain=SignalExplanation(
                                  inputs=[f"Call 成交量 = {call_vol:,} · Put 成交量 = {put_vol:,}",
                                          f"Call 未平仓量(OI) = {call_oi:,}"],
                                  formula=f"PCR量 = {put_vol:,}/{call_vol:,} = {pcr_vol:.2f}；量/仓 = {call_vol:,}/{call_oi:,} = {call_vol_oi:.2f}",
                                  thresholds=f"PCR量 ≤ {PCR_CALL_HEAVY} 且 量/仓 ≥ {CALL_VOL_OI_FRESH} → 强看涨下注(+20) · PCR量 ≤ {PCR_MILD_CALL} 偏多(+8)",
                                  conclusion=f"{'看涨下注命中 ↑（+20 分）' if cf_hit else '偏多但未达强下注（+' + str(delta) + ' 分）' if delta else '中性（0 分）'}",
                                  source="yfinance 期权链（近月合约聚合）")))

    # 看跌/避险压力：Put 主导
    if pcr_vol >= PCR_PUT_HEAVY or pcr_oi >= PCR_PUT_HEAVY:
        score -= 15
        pp_dir, pp_hit = "down", True
    else:
        pp_dir, pp_hit = "flat", False
    signals.append(SignalItem(key="put_pressure", label="看跌压力",
                              value=f"量 PCR {pcr_vol:.2f} · 仓 PCR {pcr_oi:.2f}",
                              direction=pp_dir, hit=pp_hit,
                              detail="Put/Call 成交量比与持仓比",
                              explain=SignalExplanation(
                                  inputs=[f"Put/Call 成交量比 = {pcr_vol:.2f}", f"Put/Call 持仓比 = {pcr_oi:.2f}"],
                                  formula=f"量 PCR = {put_vol:,}/{call_vol:,}；仓 PCR = {put_oi:,}/{call_oi:,}",
                                  thresholds=f"任一 PCR ≥ {PCR_PUT_HEAVY} → 看跌/避险主导(−15)",
                                  conclusion=f"{'Put 主导，命中 ↓（−15 分）' if pp_hit else '未达看跌阈值（0 分）'}",
                                  source="yfinance 期权链（近月合约聚合）")))

    # IV：有快照历史用 IV Rank（更可比），否则回退到水平口径
    if iv_rank_value is not None:
        if iv_rank_value >= 70:
            delta, iv_dir, iv_hit = 6, "up", True
        elif iv_rank_value >= 50:
            delta, iv_dir, iv_hit = 3, "up", False
        else:
            delta, iv_dir, iv_hit = 0, "flat", False
        iv_value, iv_detail = f"Rank {iv_rank_value:.0f}", "IV Rank（快照历史百分位）"
    elif atm_iv >= IV_ELEVATED:
        delta, iv_dir, iv_hit, iv_value, iv_detail = 6, "up", True, f"{atm_iv * 100:.0f}%", "ATM 年化 IV（水平——Rank 待快照累积）"
    elif atm_iv >= IV_MILD:
        delta, iv_dir, iv_hit, iv_value, iv_detail = 3, "up", False, f"{atm_iv * 100:.0f}%", "ATM 年化 IV（水平——Rank 待快照累积）"
    else:
        delta, iv_dir, iv_hit, iv_value, iv_detail = 0, "flat", False, f"{atm_iv * 100:.0f}%", "ATM 年化 IV（水平——Rank 待快照累积）"
    score += delta
    if iv_rank_value is not None:
        _iv_inputs = [f"当前 ATM IV = {atm_iv * 100:.0f}%", f"IV Rank（近一年百分位）= {iv_rank_value:.0f}"]
        _iv_formula = "IV Rank = (当前 IV − 一年最低) ÷ (一年最高 − 一年最低) × 100"
        _iv_thr = "Rank ≥ 70 偏高(+6) · ≥ 50 中性偏上(+3)"
    else:
        _iv_inputs = [f"当前 ATM 年化 IV = {atm_iv * 100:.0f}%", "IV Rank 待快照累积（暂用绝对水平）"]
        _iv_formula = "取行权价最接近现价的 Call/Put 隐含波动率均值"
        _iv_thr = f"IV ≥ {IV_ELEVATED * 100:.0f}% 偏高(+6) · ≥ {IV_MILD * 100:.0f}% 中性偏上(+3)"
    signals.append(SignalItem(key="iv_level", label="隐含波动率",
                              value=iv_value, direction=iv_dir, hit=iv_hit, detail=iv_detail,
                              explain=SignalExplanation(
                                  inputs=_iv_inputs, formula=_iv_formula, thresholds=_iv_thr,
                                  conclusion=f"{'偏高，市场预期有事件，命中 ↑（+' + str(delta) + ' 分）' if iv_hit else '未达偏高阈值（+' + str(delta) + ' 分）'}",
                                  source="yfinance 期权链" + ("（IV Rank 来自快照库）" if iv_rank_value is not None else ""))))

    # Call OI 变化（真·新增仓位）——来自快照库
    if oi_change_pct is not None:
        if oi_change_pct >= 10:
            delta, oi_dir, oi_hit = 8, "up", True
        elif oi_change_pct <= -10:
            delta, oi_dir, oi_hit = -8, "down", True
        else:
            delta, oi_dir, oi_hit = 0, "flat", False
        score += delta
        signals.append(SignalItem(key="oi_change", label="Call OI 变化",
                                  value=f"{oi_change_pct:+.1f}%", direction=oi_dir, hit=oi_hit,
                                  detail="近 5 日 Call 未平仓量变化（新增仓位）",
                                  explain=SignalExplanation(
                                      inputs=[f"当前 Call OI = {call_oi:,}", "对比约 5 交易日前的快照 OI"],
                                      formula=f"变化 = (当前 − 5日前) ÷ 5日前 × 100 = {oi_change_pct:+.1f}%",
                                      thresholds="≥ +10% 新增仓位(+8) · ≤ −10% 平仓(−8)",
                                      conclusion=f"{oi_change_pct:+.1f}% → {'OI 增加=真金进场，命中 ↑' if oi_hit and oi_dir == 'up' else 'OI 下降=平仓，命中 ↓' if oi_hit else '无显著变化'}（{delta:+d} 分）",
                                      source="yfinance 期权链 + 每日快照库")))

    return DimensionScore(key="positioning", label=label, question=question,
                          score=_clamp(score), status="ok", signals=signals)


# ── Fundamental 基本面 ──────────────────────────────────────────────────────

def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_fundamental(earnings: list[dict]) -> DimensionScore:
    """基于 FMP earnings-calendar：财报兑现历史（连续 Beat/Miss）、营收超预期、布局窗口。

    earnings：每条含 date / epsActual / epsEstimated / revenueActual / revenueEstimated。
    Guidance（指引方向）需 Transcript NLP，标 pending。
    """
    label, question = _meta("fundamental")

    if not earnings:
        return unavailable_dimension("fundamental", "FMP 未返回财报历史")

    today = datetime.date.today()
    past, upcoming = [], []
    for r in earnings:
        d = r.get("date")
        eps_actual = _f(r.get("epsActual"))
        if eps_actual is not None:
            past.append(r)
        elif d and str(d) >= today.isoformat():
            upcoming.append(r)
    past.sort(key=lambda r: str(r.get("date", "")), reverse=True)

    signals: list[SignalItem] = []
    score = 50.0
    has_data = False

    # 连续兑现：最近若干财季 epsActual vs epsEstimated
    beats = 0
    for r in past[:EARNINGS_LOOKBACK_QUARTERS]:
        a, e = _f(r.get("epsActual")), _f(r.get("epsEstimated"))
        if a is None or e is None:
            break
        if a > e:
            beats += 1
        else:
            break
    if past:
        has_data = True
        if beats >= 3:
            delta, es_dir, es_hit = 22, "up", True
        elif beats == 2:
            delta, es_dir, es_hit = 14, "up", True
        elif beats == 1:
            delta, es_dir, es_hit = 6, "up", False
        else:
            delta, es_dir, es_hit = -12, "down", True  # 最近一季 Miss
        score += delta
        beat_label = f"连续 {beats} 季 Beat" if beats else "最近一季 Miss"
        _eps_rows = []
        for r in past[:EARNINGS_LOOKBACK_QUARTERS]:
            a, e = _f(r.get("epsActual")), _f(r.get("epsEstimated"))
            if a is None or e is None:
                break
            _eps_rows.append(f"{str(r.get('date'))[:10]}：实际 {a} vs 预期 {e}（{'Beat' if a > e else 'Miss'}）")
        signals.append(SignalItem(key="earnings_surprise", label="财报兑现",
                                  value=beat_label, direction=es_dir, hit=es_hit,
                                  detail="epsActual vs epsEstimated",
                                  explain=SignalExplanation(
                                      inputs=_eps_rows or ["无历史财报"],
                                      formula="从最近一季往前数，连续 epsActual > epsEstimated 的季数",
                                      thresholds="连 ≥3 季(+22) · 连 2 季(+14) · 连 1 季(+6) · 最近一季 Miss(−12)",
                                      conclusion=f"{beat_label} → {'兑现能力强，命中 ↑' if es_hit and es_dir == 'up' else '兑现不佳，命中 ↓' if es_hit else '偏弱'}（{delta:+d} 分）",
                                      source="FMP earnings-calendar")))

    # 营收超预期：最近一季 revenueActual vs revenueEstimated
    if past:
        a, e = _f(past[0].get("revenueActual")), _f(past[0].get("revenueEstimated"))
        if a is not None and e is not None and e != 0:
            has_data = True
            rev_pct = (a - e) / e * 100
            if rev_pct >= 2:
                delta, rs_dir, rs_hit = 12, "up", True
            elif rev_pct <= -2:
                delta, rs_dir, rs_hit = -12, "down", True
            else:
                delta, rs_dir, rs_hit = 0, "flat", False
            score += delta
            signals.append(SignalItem(key="revenue_surprise", label="营收超预期",
                                      value=f"{rev_pct:+.1f}%", direction=rs_dir, hit=rs_hit,
                                      detail="最近一季 revenueActual vs revenueEstimated",
                                      explain=SignalExplanation(
                                          inputs=[f"最近一季实际营收 = {a:,.0f}", f"分析师预期营收 = {e:,.0f}"],
                                          formula=f"超预期 = ({a:,.0f} − {e:,.0f}) ÷ {e:,.0f} × 100 = {rev_pct:+.1f}%",
                                          thresholds="≥ +2% 超预期(+12) · ≤ −2% 不及预期(−12)",
                                          conclusion=f"{rev_pct:+.1f}% → {'营收超预期，命中 ↑' if rs_hit and rs_dir == 'up' else '不及预期，命中 ↓' if rs_hit else '符合预期'}（{delta:+d} 分）",
                                          source="FMP earnings-calendar")))

    # 布局窗口：距下次财报天数
    if upcoming:
        upcoming.sort(key=lambda r: str(r.get("date", "")))
        try:
            nd = datetime.date.fromisoformat(str(upcoming[0]["date"])[:10])
            days = (nd - today).days
            in_window = 0 <= days <= EARNINGS_WINDOW_DAYS
            signals.append(SignalItem(key="earnings_date", label="财报窗口",
                                      value=f"距财报 {days} 天", direction="up" if in_window else "flat",
                                      hit=in_window, detail="资金布局窗口",
                                      explain=SignalExplanation(
                                          inputs=[f"下次财报日 = {str(upcoming[0]['date'])[:10]}", f"距今 = {days} 天"],
                                          formula="距今天数 = 下次财报日 − 今日",
                                          thresholds=f"0–{EARNINGS_WINDOW_DAYS} 天内视为资金布局窗口(+5)",
                                          conclusion=f"距财报 {days} 天 → {'在布局窗口内（+5 分）' if in_window else '尚未进入窗口（0 分）'}",
                                          source="FMP earnings-calendar")))
            if in_window:
                score += 5
        except (ValueError, KeyError):
            pass

    # Guidance——需 Transcript NLP
    signals.append(SignalItem(key="guidance", label="指引方向", direction="flat", hit=False,
                              detail="需 Transcript NLP 抽取（后续）"))

    status = "ok" if has_data else "partial"
    return DimensionScore(key="fundamental", label=label, question=question,
                          score=_clamp(score), status=status, signals=signals)


# ── Confirmation 确认 ───────────────────────────────────────────────────────

def compute_confirmation(insider_stats: list[dict]) -> DimensionScore:
    """基于 FMP insider-trading/statistics 的内部人交易（近 2 季）。

    13F 需 FMP Ultimate 版、ETF Flow 为行业级——两者标 pending。
    """
    label, question = _meta("confirmation")

    signals: list[SignalItem] = []
    score = 50.0
    has_data = False

    if insider_stats:
        recent = sorted(insider_stats,
                        key=lambda r: (r.get("year", 0), r.get("quarter", 0)),
                        reverse=True)[:INSIDER_LOOKBACK_QUARTERS]
        total_purchases = sum(int(r.get("totalPurchases") or 0) for r in recent)
        total_sales = sum(int(r.get("totalSales") or 0) for r in recent)
        ratios = [_f(r.get("acquiredDisposedRatio")) for r in recent]
        ratios = [x for x in ratios if x is not None]
        avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0

        if recent:
            has_data = True
            if total_purchases > 0:
                delta, in_dir, in_hit = 20, "up", True
                detail = f"内部人开放市场买入 {total_purchases} 笔"
            elif avg_ratio >= INSIDER_ACCUM_RATIO:
                delta, in_dir, in_hit = 8, "up", False
                detail = f"净增持（增/减比 {avg_ratio:.2f}）"
            elif avg_ratio <= INSIDER_DISTRIB_RATIO and total_sales >= INSIDER_DISTRIB_SALES:
                delta, in_dir, in_hit = -12, "down", True
                detail = f"集中减持（增/减比 {avg_ratio:.2f}，卖出 {total_sales} 笔）"
            else:
                delta, in_dir, in_hit = 0, "flat", False
                detail = f"常规交易（增/减比 {avg_ratio:.2f}）"
            score += delta
            signals.append(SignalItem(key="insider", label="内部人交易",
                                      value=("买入" if total_purchases > 0 else f"增/减 {avg_ratio:.2f}"),
                                      direction=in_dir, hit=in_hit, detail=detail,
                                      explain=SignalExplanation(
                                          inputs=[f"开放市场买入(P) = {total_purchases} 笔",
                                                  f"增持/减持比(acquiredDisposedRatio) = {avg_ratio:.2f}",
                                                  f"卖出(S) = {total_sales} 笔"],
                                          formula=f"近 {INSIDER_LOOKBACK_QUARTERS} 季汇总，优先看开放市场买入，其次看增/减比",
                                          thresholds=f"有开放买入 → 强信心(+20) · 增/减比 ≥ {INSIDER_ACCUM_RATIO} 净增持(+8) · ≤ {INSIDER_DISTRIB_RATIO} 且卖出 ≥ {INSIDER_DISTRIB_SALES} 笔 集中减持(−12)",
                                          conclusion=f"{detail} → {'命中 ↑' if in_hit and in_dir == 'up' else '命中 ↓' if in_hit else '中性'}（{delta:+d} 分）",
                                          source="FMP insider-trading/statistics")))

    if not has_data:
        return unavailable_dimension("confirmation", "无内部人交易数据")

    # 13F / ETF Flow —— pending
    signals.append(SignalItem(key="institutional_13f", label="13F 机构持仓",
                              direction="flat", hit=False, detail="需 FMP Ultimate 版（后续）"))
    signals.append(SignalItem(key="etf_flow", label="ETF 资金流",
                              direction="flat", hit=False, detail="行业级，复用 ETF 模块（后续）"))

    return DimensionScore(key="confirmation", label=label, question=question,
                          score=_clamp(score), status="ok", signals=signals)
