"""tests/services/push 专用夹具：默认伪装 APNs 已配置。

测试环境（.env.development）不会填真实的 APNS_KEY_ID/TEAM_ID/PRIVATE_KEY
（这些是生产密钥，不应进测试环境），但大多数 notifier 测试关心的是「已配置时
按 locale 分组发送」的正常路径，因此这里 autouse 打个桩让 is_configured()
默认为 True。需要测试「未配置」分支的用例（见 test_skipped_when_not_configured）
会直接 monkeypatch notifier._apns_configured，覆盖掉这里的默认值。
"""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _fake_apns_configured(monkeypatch):
    monkeypatch.setattr(settings, "APNS_KEY_ID", "fake-key-id")
    monkeypatch.setattr(settings, "APNS_TEAM_ID", "fake-team-id")
    monkeypatch.setattr(settings, "APNS_PRIVATE_KEY", "fake-private-key")
