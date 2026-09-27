import pytest

from app.services.signal_radar import service as svc


@pytest.fixture(autouse=True)
def _no_background_backfill(monkeypatch):
    """默认不起后台补算（避免测试结束时留下挂起的任务）；补算相关测试自己打开。"""
    monkeypatch.setattr(svc, "_BACKFILL_DELAYS", ())
