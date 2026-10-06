"""联系我们（用户反馈）schemas。"""

import re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class FeedbackRequest(BaseModel):
    """用户提交的反馈内容。"""

    email: str = Field(..., max_length=254, description="用户填写的联系邮箱")
    content: str = Field(..., min_length=1, max_length=2000, description="反馈正文")

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("邮箱格式不正确")
        return v


class FeedbackResponse(BaseModel):
    """提交结果。"""

    sent: bool = True
