# app/schemas/vocabulary.py
"""背单词 App（WordLens）请求/响应 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.schemas.base import BaseResponse


class VocabularyUserCreate(BaseModel):
    """注册请求。"""

    email: EmailStr
    password: SecretStr = Field(..., min_length=8, max_length=64)


class VocabularyLoginRequest(BaseModel):
    """登录请求。"""

    email: EmailStr
    password: SecretStr


class VocabularyTokenResponse(BaseResponse):
    """登录/注册成功后的 token 响应。"""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class VocabularyUserResponse(BaseResponse):
    """当前用户个人信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    """修改密码请求。"""

    old_password: SecretStr
    new_password: SecretStr = Field(..., min_length=8, max_length=64)


class RecognizedWordSchema(BaseModel):
    """识别出的单个候选词。"""

    word: str
    phonetic_ipa: str
    part_of_speech: str
    definition_zh: str
    etymology: str = ""
    example_sentence: str = ""
    already_in_library: bool = False


class RecognizeResponse(BaseResponse):
    """拍照识别响应。"""

    candidates: list[RecognizedWordSchema]


class RecognizeStreamEvent(BaseModel):
    """拍照识别 NDJSON 流中的单条事件。

    事件顺序：heartbeat（每 ~5s 一次，保活）与 partial（首轮 enrich 合并后、
    以及漏词重试补全后各推一次当前已识别出的候选词）交替出现，最后以
    result（最终完整结果）或 error（识别失败）结束。
    - partial：目前已识别出的候选词快照，后续 partial/result 会整体覆盖它
      （不是增量 diff），前端直接用最新一条替换展示即可。
    """

    type: Literal["heartbeat", "partial", "result", "error"]
    stage: Literal["recognizing"] | None = None
    data: RecognizeResponse | None = None
    message: str | None = None


class VocabularyWordCreate(BaseModel):
    """批量加入生词库时的单个词。"""

    word: str = Field(..., min_length=1, max_length=100)
    phonetic_ipa: str = Field(..., max_length=100)
    part_of_speech: str = Field(..., max_length=20)
    definition_zh: str = Field(..., max_length=500)
    etymology: str = Field(default="", max_length=500)
    example_sentence: str = Field(default="", max_length=1000)


class WordsBatchCreateRequest(BaseModel):
    """批量加入生词库请求。"""

    words: list[VocabularyWordCreate] = Field(..., min_length=1)


class VocabularyWordResponse(BaseModel):
    """单词详情。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    word: str
    phonetic_ipa: str
    part_of_speech: str
    definition_zh: str
    etymology: str
    example_sentence: str
    status: str
    repetition_count: int
    easiness_factor: float
    interval_days: int
    next_review_at: datetime
    last_reviewed_at: datetime | None
    created_at: datetime


class WordsBatchCreateResponse(BaseResponse):
    """批量加入结果。"""

    created: list[VocabularyWordResponse]
    skipped_existing: list[str]


class VocabularyWordListResponse(BaseResponse):
    """生词库列表。"""

    words: list[VocabularyWordResponse]


class ReviewQueueResponse(BaseResponse):
    """待复习队列。"""

    words: list[VocabularyWordResponse]


class ReviewSubmitRequest(BaseModel):
    """提交复习结果请求。"""

    rating: int = Field(..., ge=0, le=2, description="0=不认识 1=模糊 2=认识")


class ReviewSubmitResponse(BaseResponse):
    """提交复习结果后的最新单词状态。"""

    word: VocabularyWordResponse
