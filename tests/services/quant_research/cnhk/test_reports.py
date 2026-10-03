"""累计口径 → 单季换算：TTM / 同比 / 上一完整财年合计必须与原始累计值精确一致。"""

from app.services.quant_research.cnhk.reports import (
    fiscal_position,
    merge_reports,
    quarter_end,
    to_quarters,
)
from app.services.quant_research.inputs import fiscal_year_actual, ttm


def _r(d: str, rev, *, fy_end="12-31", notice=None, **kw):
    base = {"report_date": d, "notice_date": notice or d, "fy_end": fy_end, "revenue": rev}
    for f in ("gross", "ebit", "net", "eps", "pretax", "tax", "da", "ocf", "cfi", "cff", "capex"):
        base.setdefault(f, kw.get(f))
    return base


def test_fiscal_position_calendar_and_march_year():
    assert fiscal_position("2026-06-30", "12-31") == (2026, 2)
    assert fiscal_position("2025-12-31", "12-31") == (2025, 4)
    # 3 月年结：截至 2026-06-30 是 FY2027 第 1 季；截至 2026-03-31 是 FY2026 全年
    assert fiscal_position("2026-06-30", "03-31") == (2027, 1)
    assert fiscal_position("2026-03-31", "03-31") == (2026, 4)
    assert fiscal_position("2026-05-15", "12-31") is None


def test_quarter_end():
    assert quarter_end(2026, 2, "12-31").isoformat() == "2026-06-30"
    assert quarter_end(2027, 1, "03-31").isoformat() == "2026-06-30"
    assert quarter_end(2026, 4, "06-30").isoformat() == "2026-06-30"


def test_a_share_quarterly_cumulative_is_exact():
    # 2025：Q1 10、H1 25、9M 45、FY 70；2026：Q1 12、H1 30
    reps = [_r("2025-03-31", 10), _r("2025-06-30", 25), _r("2025-09-30", 45), _r("2025-12-31", 70),
            _r("2026-03-31", 12), _r("2026-06-30", 30), _r("2024-12-31", 60), _r("2024-09-30", 40),
            _r("2024-06-30", 22), _r("2024-03-31", 9)]
    inc, cash = to_quarters(reps)
    assert [q["date"] for q in inc[:3]] == ["2026-06-30", "2026-03-31", "2025-12-31"]
    assert [q["revenue"] for q in inc[:6]] == [18, 12, 25, 20, 15, 10]
    # TTM = 2025 全年 − 2025H1 + 2026H1 = 70 − 25 + 30
    assert ttm(inc, "revenue") == 75
    assert ttm(inc, "revenue", 4) == 60 - 22 + 25
    assert fiscal_year_actual(inc, "revenue") == ("2025", 70)
    assert inc[0]["periodLabel"] == "H1" and inc[1]["periodLabel"] == "Q1"
    assert len(cash) == len(inc)


def test_hk_semiannual_spreads_evenly_but_ttm_exact():
    reps = [_r("2024-06-30", 40), _r("2024-12-31", 100), _r("2025-06-30", 50), _r("2025-12-31", 120),
            _r("2026-06-30", 70)]
    inc, _ = to_quarters(reps)
    assert [q["revenue"] for q in inc[:4]] == [35, 35, 35, 35]
    assert ttm(inc, "revenue") == 120 - 50 + 70
    assert inc[0]["periodLabel"] == "H1"
    assert fiscal_year_actual(inc, "revenue") == ("2025", 120)


def test_missing_field_points_spread_over_gap():
    # 折旧摊销只在中报 / 年报披露：一季度、三季度从相邻已知点摊开
    reps = [_r("2025-03-31", 10, da=None), _r("2025-06-30", 25, da=8), _r("2025-09-30", 45, da=None),
            _r("2025-12-31", 70, da=20)]
    inc, _ = to_quarters(reps)
    # 2025Q1~Q2 = 8/2，Q3~Q4 = (20−8)/2；EBITDA 需要 ebit，此处 ebit 缺失 → None
    assert inc[0]["ebitda"] is None


def test_da_carried_forward_when_latest_quarter_missing():
    reps = [_r("2025-06-30", 25, ebit=5, da=8), _r("2025-12-31", 70, ebit=12, da=20),
            _r("2026-03-31", 12, ebit=3, da=None)]
    inc, _ = to_quarters(reps)
    assert inc[0]["date"] == "2026-03-31"
    assert inc[0]["ebitda"] == 3 + 6  # 沿用 2025Q4 的单季折旧摊销 (20−8)/2


def test_gap_truncates_older_quarters():
    # 缺 2024 年报：2024Q3 之后到 2025Q1 之间断开，更早的季度不再接上
    reps = [_r("2025-03-31", 10), _r("2024-09-30", 40), _r("2024-06-30", 22)]
    inc, _ = to_quarters(reps)
    assert [q["date"] for q in inc] == ["2025-03-31"]


def test_march_fiscal_year_labels():
    reps = [_r("2026-03-31", 100, fy_end="03-31"), _r("2026-06-30", 30, fy_end="03-31"),
            _r("2025-09-30", 50, fy_end="03-31")]
    inc, _ = to_quarters(reps)
    assert inc[0]["fiscalYear"] == "2027" and inc[0]["period"] == "Q1" and inc[0]["date"] == "2026-06-30"
    assert inc[1]["fiscalYear"] == "2026" and inc[1]["period"] == "Q4"


def test_merge_reports_overrides_same_period():
    old = [_r("2026-06-30", 1), _r("2026-03-31", 2)]
    new = [_r("2026-06-30", 9)]
    merged = merge_reports(old, new)
    assert [r["revenue"] for r in merged] == [9, 2]
