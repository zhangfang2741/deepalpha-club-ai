"""用户设置：LLM 模型偏好（每用户，应用于其聊天/供应链等所有 LLM 调用）。"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.v1.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.services.database import database_service
from app.services.llm.registry import llm_registry
from app.services.model_preference import is_registered_model

router = APIRouter()


class ModelOption(BaseModel):
    """可选模型条目。"""

    name: str = Field(..., description="模型名（registry 注册名）")


class ModelsResponse(BaseModel):
    """可选模型列表 + 当前偏好。"""

    provider: str = Field(..., description="当前 LLM provider")
    default: str = Field(..., description="系统默认模型名")
    current: Optional[str] = Field(None, description="当前用户偏好模型名（未设置为 null）")
    available: list[str] = Field(default_factory=list, description="当前 provider 已注册的可选模型")


class PreferredModelRequest(BaseModel):
    """设置偏好模型的请求体（model 为 null 或空字符串表示清除，回退默认）。"""

    model: Optional[str] = Field(None, description="要设置的模型名；null/空清除偏好")


@router.get("/models", response_model=ModelsResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS.get("default", ["100/minute"])[0])
async def list_models(request: Request, user: User = Depends(get_current_user)) -> ModelsResponse:
    """列出当前 provider 可选模型与用户当前偏好。"""
    return ModelsResponse(
        provider=settings.LLM_PROVIDER,
        default=settings.DEFAULT_LLM_MODEL,
        current=user.preferred_model,
        available=llm_registry.get_all_names(),
    )


@router.put("/preferred-model", response_model=ModelsResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS.get("default", ["100/minute"])[0])
async def set_preferred_model(
    request: Request,
    payload: PreferredModelRequest,
    user: User = Depends(get_current_user),
) -> ModelsResponse:
    """设置当前用户的偏好模型（仅接受已注册模型；空值清除偏好）。"""
    model = (payload.model or "").strip()
    if model and not is_registered_model(model):
        raise HTTPException(
            status_code=400,
            detail=f"未注册的模型：{model}。可选：{', '.join(llm_registry.get_all_names())}",
        )
    updated = await asyncio.to_thread(
        database_service.update_user, user.id, None, None, model
    )
    logger.info("user_preferred_model_updated", user_id=user.id, model=model or None)
    return ModelsResponse(
        provider=settings.LLM_PROVIDER,
        default=settings.DEFAULT_LLM_MODEL,
        current=updated.preferred_model,
        available=llm_registry.get_all_names(),
    )
