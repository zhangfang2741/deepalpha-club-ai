"""雷达定时预热 / 盘中次级别刷新覆盖的口径：新版 App 用严格口径，线上旧版 App 用宽松（默认）口径。"""
from app.services.chan.signal_policy import DEFAULT_MODE, SIGNAL_POLICIES
from app.services.signal_radar import scheduler


def test_prewarm_covers_all_modes() -> None:
    """新版 App 改用严格口径，旧版仍请求宽松（默认）口径：两套都预热，默认口径先跑。"""
    assert len(SIGNAL_POLICIES) > 1
    assert scheduler._modes() == [DEFAULT_MODE, "medium", "strict"]
    assert all(m in SIGNAL_POLICIES for m in scheduler._modes())


def test_demo_targets_default_and_strict_first() -> None:
    """免费示例日预热：默认指数在前、严格口径（新版 App）在前；defaults_only 只含默认指数。"""
    targets = scheduler._demo_targets()
    assert targets, "没有预热目标"
    assert targets[0][0].is_default and targets[0][1] == "medium"
    seen_non_default = False
    for u, _ in targets:
        if not u.is_default:
            seen_non_default = True
        else:
            assert not seen_non_default, "默认指数必须排在非默认指数前面"
    assert all(u.is_default for u, _ in scheduler._demo_targets(defaults_only=True))
    assert {m for _, m in targets} == set(scheduler._modes())
