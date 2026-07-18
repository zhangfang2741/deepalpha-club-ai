"""解析用户偏好的 LLM 模型名（回退系统默认）。

用户在设置里选择的模型存于 ``User.preferred_model``。本模块统一把「用户 → 有效模型名」
的解析逻辑收敛到一处，供聊天（Deep Agent）与供应链等模块复用，确保：
- 只返回当前 provider 已注册的模型名，未注册/为空时返回 None（调用方回退默认）。
"""

import asyncio
from typing import Optional, Union

from app.services.database import database_service
from app.services.llm.registry import llm_registry


def is_registered_model(name: Optional[str]) -> bool:
    """判断模型名是否为当前 provider 已注册的模型。"""
    return bool(name) and name in llm_registry.get_all_names()


async def resolve_user_model(user_id: Optional[Union[str, int]]) -> Optional[str]:
    """返回该用户偏好的、且当前已注册的模型名；无有效偏好时返回 None。

    Args:
        user_id: 用户 ID（字符串或整数）。

    Returns:
        Optional[str]: 有效的偏好模型名，或 None（调用方回退系统默认）。
    """
    if user_id is None:
        return None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    user = await asyncio.to_thread(database_service.get_user, uid)
    name = getattr(user, "preferred_model", None) if user else None
    return name if is_registered_model(name) else None
