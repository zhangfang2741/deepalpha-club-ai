"""A 股 / 港股报表：累计口径报告 → 单季序列（字段名与 FMP 季度报表一致，直接喂给美股同一条管线）。纯函数。

两地报表都是「本财年至今」的累计值（A 股一季 / 半年 / 三季 / 年报；港股多为半年 + 年报，少数按季）。
换算规则（每个字段独立处理）：同一财年内，相邻两个已知累计点之差平均摊到其间各季；财年首个已知点从 0 起算。
这样 TTM、同比、3 年复合、上一完整财年合计都与原始累计值精确一致，只有被摊开的单季是近似值（页面不展示单季）。

例外：A 股一季报 / 三季报常不披露现金流量表补充资料（折旧摊销），对应季度沿用最近一季的折旧摊销
（只影响 EBITDA；不这样做的话 EBITDA 一年里有一半时间缺失）。

归一化后的累计报告（每条一个报告期）：
    {"report_date": "2026-06-30", "notice_date": "2026-08-15", "fy_end": "12-31",
     "revenue", "gross", "ebit", "net", "eps", "pretax", "tax", "da", "ocf", "cfi", "cff", "capex"}
capex 为负数（现金流出，与 FMP 一致）；缺失为 None。
"""

from __future__ import annotations

from datetime import date, timedelta

INCOME_FIELDS = ("revenue", "gross", "ebit", "net", "eps", "pretax", "tax", "da")
CASH_FIELDS = ("ocf", "cfi", "cff", "capex")
_LABELS = {1: "Q1", 2: "H1", 3: "Q3", 4: "Q4"}


def _month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def fy_end_month(fy_end: str | None) -> int:
    """财年截止「MM-DD」→ 月份（缺失或异常按 12 月）。"""
    try:
        m = int(str(fy_end or "12-31").split("-")[0])
    except ValueError:
        return 12
    return m if 1 <= m <= 12 else 12


def fiscal_position(report_date: str, fy_end: str | None) -> tuple[int, int] | None:
    """报告期 → (财年, 第几季累计)。财年按截止日所在年份命名（3 月年结、截至 2026-06-30 → FY2027 的第 1 季）。

    报告期不在季末（非 3 个月整数倍）返回 None。
    """
    d = date.fromisoformat(report_date[:10])
    end_m = fy_end_month(fy_end)
    fy = d.year if d.month <= end_m else d.year + 1
    months_left = (end_m - d.month) % 12          # 距财年截止还有几个月
    elapsed = 12 - months_left
    if elapsed % 3 or d != _month_end(d.year, d.month):
        return None
    return fy, elapsed // 3


def quarter_end(fy: int, q: int, fy_end: str | None) -> date:
    """财年 fy 第 q 季的季末日期。"""
    end_m = fy_end_month(fy_end)
    months_before_end = (4 - q) * 3
    m = end_m - months_before_end
    y = fy
    while m <= 0:
        m += 12
        y -= 1
    return _month_end(y, m)


def _spread(points: dict[int, float]) -> dict[int, float]:
    """一个字段在同一财年内的累计点 {季: 累计值} → 单季值；最后一个已知点之后的季度不给值。"""
    out: dict[int, float] = {}
    prev_q, prev_v = 0, 0.0
    for q in sorted(points):
        step = (points[q] - prev_v) / (q - prev_q)
        for k in range(prev_q + 1, q + 1):
            out[k] = step
        prev_q, prev_v = q, points[q]
    return out


def to_quarters(reports: list[dict]) -> tuple[list[dict], list[dict]]:
    """累计报告 → (利润表单季, 现金流单季)，均为新 → 旧、季度连续（遇到缺口即截断更早的部分）。"""
    by_fy: dict[int, dict[int, dict]] = {}
    fy_end = None
    for r in reports:
        pos = fiscal_position(r["report_date"], r.get("fy_end"))
        if pos is None:
            continue
        fy_end = fy_end or r.get("fy_end")
        fy, q = pos
        by_fy.setdefault(fy, {})[q] = r
    if not by_fy:
        return [], []

    singles: dict[tuple[int, int], dict] = {}
    for fy, rows in by_fy.items():
        top = max(rows)
        per_field = {}
        for f in INCOME_FIELDS + CASH_FIELDS:
            pts = {q: float(r[f]) for q, r in rows.items() if r.get(f) is not None}
            per_field[f] = _spread(pts)
        for q in range(1, top + 1):
            closing_q = min(k for k in rows if k >= q)  # 披露这一季数据的那份报告
            singles[(fy, q)] = {"fields": {f: per_field[f].get(q) for f in per_field},
                                "notice": rows[closing_q].get("notice_date"), "closing_q": closing_q}

    # 从最新一季往回走，遇到缺口就停（ttm() 依赖列表里季度连续）
    fy, q = max(singles)
    seq: list[tuple[int, int]] = []
    while (fy, q) in singles:
        seq.append((fy, q))
        fy, q = (fy, q - 1) if q > 1 else (fy - 1, 4)

    _carry_forward_da(singles, seq)
    income, cash = [], []
    for i, (fy, q) in enumerate(seq):
        s = singles[(fy, q)]
        v = s["fields"]
        d = quarter_end(fy, q, fy_end).isoformat()
        ebitda = v["ebit"] + v["da"] if v["ebit"] is not None and v["da"] is not None else None
        label = _LABELS.get(s["closing_q"], f"Q{q}") if i == 0 else f"Q{q}"
        income.append({
            "date": d, "fiscalYear": str(fy), "period": f"Q{q}", "periodLabel": label,
            "filingDate": s["notice"], "revenue": v["revenue"], "grossProfit": v["gross"], "ebit": v["ebit"],
            "ebitda": ebitda, "netIncome": v["net"], "epsDiluted": v["eps"], "incomeBeforeTax": v["pretax"],
            "incomeTaxExpense": v["tax"],
        })
        cash.append({
            "date": d, "fiscalYear": str(fy), "period": f"Q{q}",
            "operatingCashFlow": v["ocf"], "netCashProvidedByOperatingActivities": v["ocf"],
            "netCashProvidedByInvestingActivities": v["cfi"], "netCashProvidedByFinancingActivities": v["cff"],
            "capitalExpenditure": v["capex"],
        })
    return income, cash


def _carry_forward_da(singles: dict[tuple[int, int], dict], seq: list[tuple[int, int]]) -> None:
    """折旧摊销缺失的季度沿用更早一季的值（从旧到新填）。"""
    last = None
    for key in reversed(seq):
        v = singles[key]["fields"]
        if v["da"] is None:
            v["da"] = last
        else:
            last = v["da"]


def latest_report(reports: list[dict]) -> dict | None:
    """报告期最新的一份。"""
    return max(reports, key=lambda r: r["report_date"]) if reports else None


def merge_reports(old: list[dict], new: list[dict]) -> list[dict]:
    """按报告期合并（新数据覆盖同一报告期），新 → 旧排序。"""
    by_date = {r["report_date"]: r for r in old}
    for r in new:
        by_date[r["report_date"]] = r
    return sorted(by_date.values(), key=lambda r: r["report_date"], reverse=True)
