# app/schemas/vocabulary.py
"""背单词 App（WordLens）请求/响应 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.schemas.base import BaseResponse


class VocabularyUserCreate(BaseModel):
    """注册请求。code 是 /register/request-code 发到邮箱的验证码。"""

    email: EmailStr
    password: SecretStr = Field(..., min_length=6, max_length=64)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


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
    email: str | None = None
    phone: str | None = None
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    """修改密码请求。"""

    old_password: SecretStr
    new_password: SecretStr = Field(..., min_length=6, max_length=64)


class PhoneCodeRequest(BaseModel):
    """请求给手机号发验证码。号码在服务端归一化，前端不必自己处理格式。"""

    phone: str = Field(..., min_length=6, max_length=24)


class PhoneRegisterRequest(BaseModel):
    """手机号注册。"""

    phone: str = Field(..., min_length=6, max_length=24)
    password: SecretStr = Field(..., min_length=6, max_length=64)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class PhoneLoginRequest(BaseModel):
    """手机号 + 密码登录。"""

    phone: str = Field(..., min_length=6, max_length=24)
    password: SecretStr


class PhonePasswordResetConfirm(BaseModel):
    """凭手机验证码设置新密码。"""

    phone: str = Field(..., min_length=6, max_length=24)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: SecretStr = Field(..., min_length=6, max_length=64)


class RegisterCodeRequest(BaseModel):
    """请求给待注册邮箱发验证码。"""

    email: EmailStr


class PasswordResetRequest(BaseModel):
    """请求发送找回密码的验证码。"""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """凭验证码设置新密码。"""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: SecretStr = Field(..., min_length=6, max_length=64)


class DeleteAccountRequest(BaseModel):
    """删除账号请求：必须带当前密码二次确认。

    光凭 token 就能删号太危险（手机丢了、token 被拿走都会造成不可恢复的数据
    丢失），要求重新输一次密码。
    """

    password: SecretStr


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


class WordsBatchDeleteRequest(BaseModel):
    """批量删除生词请求；限制单批规模，避免数据库参数和事务无限膨胀。"""

    word_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=5000)


class WordsBatchDeleteResponse(BaseResponse):
    """批量删除结果；不存在或已被删除的 ID 按幂等成功处理。"""

    deleted_count: int


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


class VocabularyStatsResponse(BaseResponse):
    """生词库计数汇总，供 iOS 播放列表面板一次性展示各分组的词数。

    没有它的话客户端得把整个生词库拉下来自己数，播放列表面板每次打开都要传
    几百条词的完整 payload 只为了显示四个数字。
    """

    due_count: int
    new_count: int
    fuzzy_count: int
    known_count: int
    total_count: int


class PlaylistResponse(BaseResponse):
    """自定义歌单（含词数）。"""

    id: uuid.UUID
    name: str
    word_count: int
    created_at: datetime


class PlaylistListResponse(BaseResponse):
    """歌单列表。"""

    playlists: list[PlaylistResponse]


class PlaylistCreateRequest(BaseModel):
    """新建歌单。word_ids 可以为空，先建空歌单再往里加词也是合理流程。"""

    name: str = Field(..., min_length=1, max_length=50)
    word_ids: list[uuid.UUID] = Field(default_factory=list)


class PlaylistUpdateRequest(BaseModel):
    """改名 / 整体替换词表。两个字段都可选，传 None 表示这一项不动。"""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    word_ids: list[uuid.UUID] | None = Field(default=None)


class PlaylistAddWordsRequest(BaseModel):
    """把一批词并入歌单末尾（生词库多选「加入歌单」用）。"""

    word_ids: list[uuid.UUID] = Field(..., min_length=1)
