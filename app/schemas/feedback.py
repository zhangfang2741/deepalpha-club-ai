"""联系我们（用户反馈）schemas。"""

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    """用户提交的反馈内容。"""

    content: str = Field(..., min_length=1, max_length=2000, description="反馈正文")


class FeedbackResponse(BaseModel):
    """提交结果。"""

    sent: bool = True
