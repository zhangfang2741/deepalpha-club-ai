"""通用公式：无论真实数据是否齐全，都能说明指标的计算方式。

复用计算层输入标签；具体代入和结果仍由 copy.metric_expression 生成。
"""

from app.services.quant_research.metrics import INPUT_LABELS, MOMENTUM_WINDOWS, MetricDef

# 倍数与利润率的分子、分母；期间口径复用原始数据标签。
_RATIO_INPUTS: dict[str, tuple[str, str]] = {
    "pe_ttm": ("price", "eps_ttm"),
    "pe_fwd": ("price", "eps_ntm"),
    "ps_ttm": ("market_cap", "rev_ttm"),
    "ps_fwd": ("market_cap", "rev_ntm"),
    "ev_sales_ttm": ("ev", "rev_ttm"),
    "ev_sales_fwd": ("ev", "rev_ntm"),
    "ev_ebitda_ttm": ("ev", "ebitda_ttm"),
    "ev_ebitda_fwd": ("ev", "ebitda_ntm"),
    "ev_ebit_ttm": ("ev", "ebit_ttm"),
    "ev_ebit_fwd": ("ev", "ebit_ntm"),
    "pb": ("market_cap", "equity"),
    "pcf": ("market_cap", "ocf_ttm"),
    "gross_m": ("gross_ttm", "rev_ttm"),
    "ebit_m": ("ebit_ttm", "rev_ttm"),
    "ebitda_m": ("ebitda_ttm", "rev_ttm"),
    "net_m": ("net_ttm", "rev_ttm"),
    "fcf_m": ("fcf_ttm", "rev_ttm"),
    "roe": ("net_ttm", "equity"),
    "roa": ("net_ttm", "assets"),
    "roic": ("nopat", "invested"),
    "asset_turn": ("rev_ttm", "assets"),
}


def metric_calculation(metric: MetricDef, lang: str) -> str:
    """返回百分比或倍数口径的符号公式；不填补数据、不参与计算。"""
    key = metric.key
    language_index = 0 if lang == "zh" else 1
    if key in _RATIO_INPUTS:
        numerator, denominator = _RATIO_INPUTS[key]
        expression = f"{INPUT_LABELS[numerator][language_index]} ÷ {INPUT_LABELS[denominator][language_index]}"
        return expression + (" × 100%" if metric.unit == "pct" else "")
    if key in ("peg_ttm", "peg_fwd"):
        return (
            ("市盈率 TTM ÷ 最近一年 EPS 增速（百分数，例如 20% 取 20）",
             "P/E (TTM) ÷ trailing EPS growth (percent number: 20% means 20)")
            if key == "peg_ttm" else
            ("前瞻市盈率 ÷ 下一财年相对本财年的 EPS 预期增速（百分数，例如 20% 取 20）",
             "P/E (FWD) ÷ expected FY2 vs FY1 EPS growth (percent number: 20% means 20)")
        )[language_index]
    if key == "rev_cagr3":
        return (
            "[(营收 TTM ÷ 3 年前同期营收)^(1/3) − 1] × 100%",
            "[(Revenue TTM ÷ revenue 3Y ago)^(1/3) − 1] × 100%",
        )[language_index]
    if metric.dimension == "growth":
        prefix, period = key.rsplit("_", 1)
        current = f"{prefix}_ttm" if period == "yoy" else f"{prefix}_fy1"
        previous = f"{prefix}_ttm_prev" if period == "yoy" else f"{prefix}_fy0"
        return f"({INPUT_LABELS[current][language_index]} ÷ {INPUT_LABELS[previous][language_index]} − 1) × 100%"
    if key in MOMENTUM_WINDOWS:
        days = MOMENTUM_WINDOWS[key]
        return (
            f"(最新前复权收盘价 ÷ {days} 个交易日前的前复权收盘价 − 1) × 100%",
            f"(Latest adjusted close ÷ adjusted close {days} trading days ago − 1) × 100%",
        )[language_index]
    if metric.dimension == "revisions":
        days = 30 if key.endswith("30d") else 90
        return (
            f"(当前一致预期 − {days} 天前一致预期) ÷ |{days} 天前一致预期| × 100%（同一财年）",
            f"(Current consensus − consensus {days} days ago) ÷ |consensus {days} days ago| × 100% (same fiscal year)",
        )[language_index]
    if metric.dimension == "moat":
        return {
            "moat_gm_avg": ("(4 个年度毛利率之和) ÷ 4，每个年度 = 12 个月毛利 ÷ 12 个月营收",
                            "(Sum of four 12-month gross margins) ÷ 4; each = 12-month gross profit ÷ 12-month revenue"),
            "moat_gm_vol": ("4 个年度毛利率的标准差（数值越小越稳）",
                            "Standard deviation of four 12-month gross margins (smaller = steadier)"),
            "moat_gm_trend": ("最近 12 个月毛利率 − 3 年前同期毛利率",
                              "Gross margin, last 12 months − gross margin, same 12 months 3 years earlier"),
            "moat_om_min": ("4 个年度 EBIT 利润率中最低的一个", "Lowest of four 12-month EBIT margins"),
            "moat_om_vol": ("4 个年度 EBIT 利润率的标准差（数值越小越稳）",
                            "Standard deviation of four 12-month EBIT margins (smaller = steadier)"),
            "moat_fcf_conv": ("近 2 年自由现金流合计 ÷ 近 2 年净利润合计 × 100%",
                              "Two-year free cash flow ÷ two-year net income × 100%"),
        }[key][language_index]
    raise ValueError(f"指标缺少通用公式：{key}")
