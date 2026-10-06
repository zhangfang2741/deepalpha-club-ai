"""联系我们：用户提交一段文字，转成邮件发给运营邮箱。"""

import html

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services import email as email_service

router = APIRouter()


@router.post("", response_model=FeedbackResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_feedback"][0])
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
) -> FeedbackResponse:
    """提交反馈，邮件发往 FEEDBACK_TO_EMAIL。"""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="内容不能为空")
    if not settings.FEEDBACK_TO_EMAIL or not email_service.is_configured():
        raise HTTPException(status_code=503, detail="反馈服务暂未开通")

    account = user.email or user.phone or f"user#{user.id}"
    subject = f"[{settings.CHAN_BRAND_NAME}] 用户反馈 - {body.email}"
    text = f"联系邮箱：{body.email}\n账号：{account}（ID {user.id}）\n\n{content}\n"
    page = (
        f"<p>联系邮箱：{html.escape(body.email)}</p>"
        f"<p>账号：{html.escape(account)}（ID {user.id}）</p>"
        f"<p style=\"white-space:pre-wrap\">{html.escape(content)}</p>"
    )
    try:
        await email_service.send_email(
            settings.FEEDBACK_TO_EMAIL, subject, page, text, from_name=settings.CHAN_BRAND_NAME
        )
    except (email_service.EmailNotConfiguredError, email_service.EmailSendError):
        raise HTTPException(status_code=503, detail="发送失败，请稍后再试")

    logger.info("feedback_submitted", user_id=user.id, length=len(content))
    return FeedbackResponse()
