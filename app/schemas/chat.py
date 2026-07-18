"""This file contains the chat schema for the application."""

import re
from typing import (
    List,
    Literal,
    Optional,
    Union,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.schemas.base import BaseResponse


class Message(BaseModel):
    """Message model for chat endpoint.

    Attributes:
        role: The role of the message sender (user or assistant).
        content: The content of the message.
    """

    model_config = {"extra": "ignore"}

    role: Literal["user", "assistant", "system"] = Field(..., description="The role of the message sender")
    content: str = Field(..., description="The content of the message", min_length=1, max_length=3000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate the message content.

        Args:
            v: The content to validate

        Returns:
            str: The validated content

        Raises:
            ValueError: If the content contains disallowed patterns
        """
        # Check for potentially harmful content
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("Content contains potentially harmful script tags")

        # Check for null bytes
        if "\0" in v:
            raise ValueError("Content contains null bytes")

        return v


class ChatRequest(BaseModel):
    """Request model for chat endpoint.

    Attributes:
        messages: List of messages in the conversation.
    """

    messages: List[Message] = Field(
        ...,
        description="List of messages in the conversation",
        min_length=1,
    )


class LangGraphMessageInput(BaseModel):
    """assistant-ui useLangGraphRuntime 传入的单条消息（宽松解析）。

    前端 react-langgraph 发送的是 LangChain 风格消息（含 ``type`` 字段），
    ``content`` 可能是字符串或内容块数组，这里统一宽松接收后在端点里提取文本。
    """

    model_config = {"extra": "ignore"}

    type: Optional[str] = Field(default=None, description="LangChain 消息类型，如 human/ai")
    role: Optional[str] = Field(default=None, description="OpenAI 风格角色，作为 type 的回退")
    content: Union[str, list, None] = Field(default=None, description="消息内容（字符串或内容块数组）")


class LangGraphCommand(BaseModel):
    """中断恢复指令。"""

    resume: Optional[str] = Field(default=None, description="恢复被 ask_human 等中断的图执行时提供的值")


class LangGraphChatRequest(BaseModel):
    """useLangGraphRuntime 的流式请求体。"""

    messages: List[LangGraphMessageInput] = Field(
        default_factory=list, description="本轮要追加的新消息（通常仅最新一条用户消息）"
    )
    command: Optional[LangGraphCommand] = Field(default=None, description="可选的中断恢复指令")


class ChatResponse(BaseResponse):
    """Response model for chat endpoint.

    Attributes:
        messages: List of messages in the conversation.
    """

    messages: List[Message] = Field(..., description="List of messages in the conversation")


class StreamResponse(BaseResponse):
    """Response model for streaming chat endpoint.

    Attributes:
        content: The content of the current chunk.
        done: Whether the stream is complete.
    """

    content: str = Field(default="", description="The content of the current chunk")
    done: bool = Field(default=False, description="Whether the stream is complete")


class SessionTitle(BaseModel):
    """Structured output schema for session title generation."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=60,
    )

    @field_validator("title")
    @classmethod
    def _normalize(cls, v: str) -> str:
        v = " ".join(v.split()).strip(" \"'`.,:;!?-")
        if not v:
            raise ValueError("empty title after normalization")
        return v
