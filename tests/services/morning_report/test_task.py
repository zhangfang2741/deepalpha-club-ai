"""Celery 任务：幂等跳过、成功落库、失败落库不影响其他市场。"""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.services.morning_report.schema import LocalizedText

import pytest

from app.models.morning_report import MorningReport
from app.tasks import morning_report as task_mod


@pytest.mark.asyncio
async def test_skips_existing_success(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("不应触发生成")

    monkeypatch.setattr(task_mod, "_generate_one", boom)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec(self, *_a):
            class R:
                def first(self):
                    return MorningReport(market="us", trade_date=date(2026, 9, 8), status="success")

            return R()

    monkeypatch.setattr(task_mod, "get_sync_session_cm", FakeSession)
    result = await task_mod._generate(["us"])
    assert result["us"]["skipped"] is True


@pytest.mark.asyncio
async def test_generate_one_marks_failed(monkeypatch):
    class FakeSession:
        record = MorningReport(market="us", trade_date=date(2026, 9, 8))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec(self, *_a):
            class R:
                def first(self):
                    return None

            return R()

        def add(self, obj):
            pass

        def commit(self):
            pass

    async def failing_generate(market, trade_date):
        raise RuntimeError("llm down")

    monkeypatch.setattr(task_mod, "get_sync_session_cm", FakeSession)
    monkeypatch.setattr(task_mod, "generate_report", failing_generate)
    result = await task_mod._generate_one("us", date(2026, 9, 8))
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_success_result_is_json_serializable(monkeypatch):
    """Celery JSON 后端不能收到 Pydantic 摘要对象，但推送仍需完整双语摘要。"""
    session = MagicMock()
    session.__enter__.return_value.exec.return_value.first.return_value = None
    monkeypatch.setattr(task_mod, "get_sync_session_cm", lambda: session)
    summary = LocalizedText(zh="摘要", en="Summary")
    monkeypatch.setattr(task_mod, "_generate_one", AsyncMock(return_value={
        "market": "us", "status": "success", "summary": summary,
    }))
    notify = AsyncMock()
    monkeypatch.setattr(task_mod, "notify_generated", notify)
    result = await task_mod._generate(["us"])
    assert json.loads(json.dumps(result))["us"]["status"] == "success"
    notify.assert_awaited_once_with(["us"], {"us": summary})
