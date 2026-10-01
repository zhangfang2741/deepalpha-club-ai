"""雷达定时预热 / 盘中次级别刷新覆盖的口径：新版 App 用严格口径，线上旧版 App 用宽松（默认）口径。"""
from app.services.chan.signal_policy import DEFAULT_MODE, SIGNAL_POLICIES
from app.services.signal_radar import scheduler


def test_prewarm_covers_default_and_strict() -> None:
    """新版 App 改用严格口径，旧版仍请求宽松（默认）口径：两套都预热，默认口径先跑。"""
    assert len(SIGNAL_POLICIES) > 1
    assert scheduler._modes() == [DEFAULT_MODE, "strict"]
    assert all(m in SIGNAL_POLICIES for m in scheduler._modes())
