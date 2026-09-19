"""内置词库 API 端点测试（列表 + 未知词库 404）。

只覆盖不落库的路径：列表接口本身不碰 DB；导入未知词库在服务层查不到元信息时
直接 404，也在触库前返回。真正写库的导入链路由服务层去重逻辑与内置数据完整性
单测（tests/services/vocabulary/test_libraries.py）保障，这里用假依赖避免连真库。
"""
import uuid

from fastapi.testclient import TestClient

from app.api.v1.vocabulary.dependencies import get_current_vocab_user
from app.db.session import get_db
from app.main import app
from app.models.vocabulary import VocabularyUser

client = TestClient(app)


def _fake_user() -> VocabularyUser:
    return VocabularyUser(id=uuid.uuid4(), email="t@example.com", hashed_password="x")


async def _fake_db():
    # 被测路径都不会真正用到 session，给个占位值即可。
    yield object()


def _override_auth():
    app.dependency_overrides[get_current_vocab_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db


def _clear_overrides():
    app.dependency_overrides.pop(get_current_vocab_user, None)
    app.dependency_overrides.pop(get_db, None)


def test_list_libraries_returns_groups():
    _override_auth()
    try:
        resp = client.get("/api/v1/vocabulary/libraries")
    finally:
        _clear_overrides()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["groups"]) == 8
    keys = [g["key"] for g in body["groups"]]
    assert "cet" in keys and "overseas" in keys
    cet = next(g for g in body["groups"] if g["key"] == "cet")
    assert any(b["id"] == "CET4luan_1" for b in cet["books"])
    for book in cet["books"]:
        assert book["word_count"] > 0


def test_list_libraries_requires_auth():
    # 不注入假用户，HTTPBearer 缺失应拒绝。
    resp = client.get("/api/v1/vocabulary/libraries")
    assert resp.status_code in (401, 403)


def test_import_unknown_library_returns_404():
    _override_auth()
    try:
        resp = client.post("/api/v1/vocabulary/libraries/not_a_real_book/import")
    finally:
        _clear_overrides()
    assert resp.status_code == 404
