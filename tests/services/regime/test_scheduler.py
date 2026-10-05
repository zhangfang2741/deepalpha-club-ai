"""regime 每日重算：是否需要启动补跑。"""
from datetime import date

from app.services.regime.scheduler import is_stale


def test_is_stale():
    d = date(2026, 9, 30)
    assert is_stale(None, "2026-09-30", d)
    assert is_stale("2026-09-30", None, d)
    assert is_stale("2026-09-29", "2026-09-30", d)
    assert not is_stale("2026-09-30", "2026-09-30", d)


def test_is_cnhk_stale():
    from datetime import date

    from app.services.regime.scheduler import is_cnhk_stale

    assert is_cnhk_stale(None, date(2026, 9, 30))
    assert is_cnhk_stale("2026-09-29", date(2026, 9, 30))
    assert not is_cnhk_stale("2026-09-30", date(2026, 9, 30))
    assert not is_cnhk_stale("2026-10-01", date(2026, 9, 30))
