"""APNs 发送封装（aioapns，Token-Based p8 认证）。懒初始化，未配置时返回 None。"""

from typing import Any

from app.core.config import settings
from app.core.logging import logger


def is_configured() -> bool:
    """三项凭据（key id / team id / 私钥）齐全才算已配置。"""
    return bool(settings.APNS_KEY_ID and settings.APNS_TEAM_ID and settings.APNS_PRIVATE_KEY)


_client: Any = None


def get_client() -> Any:
    """懒初始化 APNs 客户端单例，避免未配置时提前构造失败。"""
    global _client
    if _client is None:
        from aioapns import APNs

        _client = APNs(
            key_id=settings.APNS_KEY_ID,
            team_id=settings.APNS_TEAM_ID,
            key=settings.APNS_PRIVATE_KEY,  # 必须是 PEM 私钥内容本身，不支持文件路径
            use_sandbox=settings.APNS_USE_SANDBOX,
            topic=settings.APNS_BUNDLE_ID,
        )
    return _client


async def send(token: str, title: str, body: str, data: dict | None = None) -> bool:
    """发送一条 alert 推送。返回是否成功；token 失效返回 False 并记日志。"""
    from aioapns import NotificationRequest, PushType

    request = NotificationRequest(
        device_token=token,
        message={
            "aps": {"alert": {"title": title, "body": body}, "sound": "default", "badge": 1},
            **(data or {}),
        },
        push_type=PushType.ALERT,
    )
    try:
        result = await get_client().send_notification(request)
    except Exception:  # noqa: BLE001 —— 推送失败不影响生成任务
        logger.exception("apns_send_error", token_prefix=token[:8])
        return False
    if not result.is_successful:
        logger.warning("apns_send_rejected", token_prefix=token[:8], description=result.description)
    return bool(result.is_successful)
