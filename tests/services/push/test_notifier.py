"""notifier：按 locale 分组、标题/正文取对应语言、未配置 APNs 时静默跳过。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.morning_report.schema import LocalizedText
from app.services.push import notifier


def _summary() -> LocalizedText:
    return LocalizedText(zh="纳指跌入回调区间", en="Nasdaq entered correction")


@pytest.mark.asyncio
async def test_sends_per_locale(monkeypatch):
    sent: list[tuple[str, str, str, dict]] = []

    async def fake_send(token, title, body, data):
        sent.append((token, title, body, data))
        return True

    monkeypatch.setattr(notifier, "_send_one", fake_send)
    tokens = [
        {"token": "tok-zh", "locale": "zh-Hans"},
        {"token": "tok-en", "locale": "en"},
    ]
    with patch.object(notifier, "_load_tokens", return_value=tokens):
        await notifier.notify_generated(["us"], {"us": _summary()})
    assert len(sent) == 2
    zh = next(s for s in sent if s[0] == "tok-zh")
    en = next(s for s in sent if s[0] == "tok-en")
    assert zh[1] == "美股晨报已生成" and "纳指" in zh[2]
    assert en[1] == "Your US Morning Brief is ready" and "Nasdaq" in en[2]
    assert zh[3] == {"market": "us"}


@pytest.mark.asyncio
async def test_cn_hk_merged_single_title(monkeypatch):
    sent: list[tuple[str, str, str, dict]] = []

    async def fake_send(token, title, body, data):
        sent.append((token, title, body, data))
        return True

    monkeypatch.setattr(notifier, "_send_one", fake_send)
    with patch.object(notifier, "_load_tokens", return_value=[{"token": "t", "locale": "zh-Hans"}]):
        await notifier.notify_generated(["cn", "hk"], {"cn": _summary(), "hk": _summary()})
    assert len(sent) == 1
    assert sent[0][1] == "A股 · 港股晨报已生成"
    assert sent[0][3] == {"market": "cn"}


@pytest.mark.asyncio
async def test_skipped_when_not_configured(monkeypatch):
    monkeypatch.setattr(notifier, "_apns_configured", lambda: False)
    # 不应抛异常（生成任务不受推送配置影响）
    await notifier.notify_generated(["us"], {"us": _summary()})
