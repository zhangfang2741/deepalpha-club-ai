from app.services.quant_research.report import _CN_COLUMNS, _HK_COLUMNS, pick_announcement


def _row(code, col, title="t", date="2026-08-31"):
    return {"art_code": code, "title": title, "notice_date": date, "columns": [{"column_name": col}]}


def test_pick_latest_periodic_report_skips_other_announcements():
    rows = [_row("AN1", "分配预案"), _row("AN2", "半年度报告摘要"), _row("AN3", "半年度报告全文", "中报"), _row("AN4", "年度报告全文")]
    out = pick_announcement(rows, _CN_COLUMNS, "zh", "600150")
    assert out and out.url.endswith("H2_AN3_1.pdf") and out.report_type == "中报" and out.file_type == "pdf"


def test_pick_hk_and_reject_bad_code():
    rows = [_row("AN/../x", "年報"), _row("AN9", "季度業績")]
    out = pick_announcement(rows, _HK_COLUMNS, "en", "00700")
    assert out and out.url.endswith("H2_AN9_1.pdf") and out.report_type == "Quarterly results"
    assert pick_announcement([_row("AN1", "分配預案")], _HK_COLUMNS, "zh", "00700") is None
