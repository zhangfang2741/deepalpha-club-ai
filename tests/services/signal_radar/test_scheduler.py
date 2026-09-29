"""雷达定时预热 / 盘中次级别刷新只覆盖 App 实际使用的默认口径。"""
from app.services.chan.signal_policy import DEFAULT_MODE, SIGNAL_POLICIES
from app.services.signal_radar import scheduler


def test_prewarm_covers_only_default_mode() -> None:
    """App 固定宽松口径：严格口径不预热（接口仍可按需现算），省下补算与 30 分钟拉数。"""
    assert len(SIGNAL_POLICIES) > 1
    assert scheduler._modes() == [DEFAULT_MODE]
