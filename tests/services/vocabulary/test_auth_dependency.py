"""WordLens 鉴权依赖的状态码语义测试。

重点是「token 签名有效、但对应用户已不存在」这一种情况必须返回 401 而不是 404。

起因：删除账号功能上线后端到端实测发现，删号后拿旧 token 请求任何接口都返回
404。而 iOS 端 APIClient 只在 401 时才广播 .apiUnauthorized 触发自动登出
（见 ios/WordLens/Networking/APIClient.swift），拿到 404 只会显示
「请求失败（404）」。结果是：账号在另一台设备上被删掉后，这台设备会卡在每个
页面都报错、又回不到登录页的死胡同里。
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.v1.vocabulary.dependencies import get_current_vocab_user


def _credentials(token: str = "header.payload.signature") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_deleted_user_yields_401_so_client_logs_out():
    """签名有效但用户已被删除 —— 认证失败，不是资源不存在。"""
    with (
        patch("app.api.v1.vocabulary.dependencies.verify_token", return_value=str(uuid.uuid4())),
        patch(
            "app.api.v1.vocabulary.dependencies.user_service.get_user_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_vocab_user(credentials=_credentials(), db=AsyncMock())

    assert exc_info.value.status_code == 401, "必须是 401，否则 iOS 端不会自动登出"


async def test_invalid_token_yields_401():
    with patch("app.api.v1.vocabulary.dependencies.verify_token", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_vocab_user(credentials=_credentials(), db=AsyncMock())

    assert exc_info.value.status_code == 401


async def test_malformed_token_yields_401():
    """verify_token 对非 JWT 三段式结构直接抛 ValueError。"""
    with patch(
        "app.api.v1.vocabulary.dependencies.verify_token",
        side_effect=ValueError("not a jwt"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_vocab_user(credentials=_credentials("garbage"), db=AsyncMock())

    assert exc_info.value.status_code == 401


async def test_valid_user_is_returned():
    user = object()
    with (
        patch("app.api.v1.vocabulary.dependencies.verify_token", return_value=str(uuid.uuid4())),
        patch(
            "app.api.v1.vocabulary.dependencies.user_service.get_user_by_id",
            AsyncMock(return_value=user),
        ),
    ):
        result = await get_current_vocab_user(credentials=_credentials(), db=AsyncMock())

    assert result is user
