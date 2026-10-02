"""regime 因子表 → 宏观格 / 行业格。"""
from app.services.macro.regime_view import (
    SectorRow,
    StateRow,
    build_state,
    sector_rows,
    state_history,
    strongest_weakest,
)


def _row(d: str, label: str | None, p=(0.7, 0.2, 0.1), raw: str | None = None) -> StateRow:
    return StateRow(d, label, raw or label, *p)


def test_state_uses_latest_and_counts_days():
    """取最新状态并数连续天数。"""
    rows = [_row("2026-09-25", "risk_off", (0.1, 0.2, 0.7)), _row("2026-09-28", "risk_on"),
            _row("2026-09-29", "risk_on"), _row("2026-09-30", "risk_on", (0.72, 0.18, 0.1))]
    st = build_state(rows)
    assert st is not None
    assert (st.label, st.label_text, st.days_in_state, st.as_of) == ("risk_on", "逐利", 3, "2026-09-30")
    assert st.probability == 0.72


def test_state_falls_back_to_raw_label_and_skips_empty():
    """没有确认标签时用原始标签，跳过空行。"""
    rows = [_row("2026-09-29", None, raw="neutral", p=(0.3, 0.5, 0.2)),
            StateRow("2026-09-30", None, None, None, None, None)]
    st = build_state(rows, lang="en")
    assert st is not None and st.label == "neutral" and st.label_text == "Neutral"
    assert build_state([]) is None


def test_sector_rows_sorted_with_counts():
    """行业按强弱排序并带买卖点数。"""
    rows = [SectorRow("d", "energy", -0.05, "risk_off", None, 0.1),
            SectorRow("d", "healthcare", 0.08, "risk_on", None, 0.8),
            SectorRow("d", "technology", None, None, None, None)]
    out = sector_rows(rows, {"healthcare": {"buy": 5, "sell": 1}})
    assert [s.key for s in out] == ["healthcare", "energy", "technology"]
    assert (out[0].name, out[0].buy_count, out[0].sell_count) == ("医疗", 5, 1)
    assert not any(s.has_children for s in out)  # 只做一级行业，不下钻


def test_strongest_weakest():
    """最强 / 最弱行业。"""
    rows = [SectorRow("d", "energy", -0.05, "risk_off", None, 0.1),
            SectorRow("d", "healthcare", 0.08, "risk_on", None, 0.8)]
    s, w = strongest_weakest(rows)
    assert s is not None and w is not None
    assert (s.key, w.key) == ("healthcare", "energy")
    assert strongest_weakest([]) == (None, None)


def test_history_fills_unconfirmed_tail_with_raw_label():
    """末尾未确认的天数用原始标签补色并标 pending，与状态卡片一致；中间的空档保持留空。"""
    rows = [_row("d1", "risk_off"), _row("d2", None, raw="neutral"), _row("d3", "risk_on"),
            _row("d4", None, raw="risk_on"), _row("d5", None, raw="risk_on")]
    pts = state_history(rows)
    assert [(p.label, p.pending) for p in pts] == [
        ("risk_off", False), (None, False), ("risk_on", False), ("risk_on", True), ("risk_on", True)]
    st = build_state(rows)
    assert st is not None and pts[-1].label == st.label


def test_history_all_confirmed_has_no_pending():
    pts = state_history([_row("d1", "risk_on"), _row("d2", "risk_on")])
    assert not any(p.pending for p in pts)
