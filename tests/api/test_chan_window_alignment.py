"""日线分析起点固定（两年，按月对齐）：雷达、详情页、自选阶段、次级别的大级别用同一个起点，
结构不随用户所选起始日期漂移。设计见 app/services/chan/window.py。

背景：缠论的中枢是从第一笔往后分组的，起点早几天多出一笔，整条序列的中枢就整体错开
（MNST 2025-10-31 三买：起点 2025-09-19 时没有，2025-10-01 时有）。
"""
from datetime import date

from app.api.v1.chan import _anchor_start, _visible_start, analysis_window
from app.services.chan.window import canonical_daily_start
from app.services.signal_radar import service as radar


def test_canonical_start_is_two_years_back_aligned_to_month_start():
    assert canonical_daily_start("2026-10-02") == "2024-10-01"
    assert canonical_daily_start("2026-10-31") == "2024-10-01"  # 往前 730 天 = 2024-10-31，取当月 1 号
    assert canonical_daily_start("2026-11-01") == "2024-11-01"  # 跨月才变
    assert canonical_daily_start(date(2026, 9, 18)) == "2024-09-01"


def test_canonical_start_changes_only_once_a_month():
    starts = {canonical_daily_start(date(2026, 9, d)) for d in range(1, 31)}
    assert len(starts) <= 2  # 每月最多跨一次边界，不是每天都变


def test_detail_anchor_ignores_user_start_date():
    """MNST 的场景：用户起点 2025-09-19 与 2025-10-01 必须取同一个分析起点。"""
    a1, v1 = analysis_window("2025-09-19", "2026-10-02", "daily")
    a2, v2 = analysis_window("2025-10-01", "2026-10-02", "daily")
    assert a1 == a2 == "2024-10-01"
    assert (v1, v2) == ("2025-09-19", "2025-10-01")  # 起点只决定显示哪一段


def test_visible_start_cannot_precede_anchor():
    anchor, visible = analysis_window("2020-01-01", "2026-10-02", "daily")
    assert visible == anchor == "2024-10-01"


def test_radar_fetch_range_equals_detail_range():
    as_of = date(2026, 10, 2)
    detail_anchor, _ = analysis_window("2026-02-03", as_of.isoformat(), "daily")
    assert radar._fetch_start(as_of, window=45) == radar._fetch_start(as_of, window=30) == detail_anchor


def test_invalid_end_date_falls_back_to_legacy_warmup():
    anchor, visible = analysis_window("2026-01-01", "not-a-date", "daily")
    assert (anchor, visible) == ("2025-07-05", "2026-01-01")


def test_weekly_and_30min_keep_visible_plus_warmup():
    assert analysis_window("2026-01-01", "2026-10-02", "weekly")[0] == _anchor_start("2026-01-01", "weekly")
    """30 分钟：可见区间最多最近 30 天、预热 20 天（合计约 50 天，在 Yahoo 分钟线 60 天上限内）。"""
    assert _visible_start("2025-09-24", "2026-09-24", "30min") == "2026-08-25"   # 一年被收窄到 30 天
    assert _visible_start("2026-09-10", "2026-09-24", "30min") == "2026-09-10"   # 本就更短则不动
    assert _anchor_start("2026-08-25", "30min", None) == "2026-08-05"
