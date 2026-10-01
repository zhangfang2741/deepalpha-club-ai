"""regime 因子表 → 宏观格 / 行业格。"""
from app.services.macro.regime_view import (
    SectorRow,
    StateRow,
    build_state,
    sector_rows,
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
            SectorRow("d", "semiconductors", 0.08, "risk_on", None, 0.8),
            SectorRow("d", "technology", None, None, None, None)]
    out = sector_rows(rows, {"semiconductors": {"buy": 5, "sell": 1}})
    assert [s.key for s in out] == ["semiconductors", "energy", "technology"]
    assert (out[0].name, out[0].buy_count, out[0].sell_count) == ("半导体", 5, 1)
    assert out[2].has_children is True


def test_strongest_weakest():
    """最强 / 最弱行业。"""
    rows = [SectorRow("d", "energy", -0.05, "risk_off", None, 0.1),
            SectorRow("d", "semiconductors", 0.08, "risk_on", None, 0.8)]
    s, w = strongest_weakest(rows)
    assert s is not None and w is not None
    assert (s.key, w.key) == ("semiconductors", "energy")
    assert strongest_weakest([]) == (None, None)
