# app/models/vocabulary.py
"""背单词 App（WordLens）数据模型：独立账户体系 + 生词库 + 复习日志。

WordLens 是与主站投研平台完全独立的产品线，因此 VocabularyUser 不复用
app/models/user.py 的 User 表，账户体系完全隔离。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import bcrypt
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


class VocabularyUser(UUIDModel, table=True):
    """WordLens 独立账户。"""

    __tablename__ = "vocabulary_users"

    email: str = Field(..., unique=True, index=True, max_length=255)
    hashed_password: str

    def verify_password(self, password: str) -> bool:
        """校验明文密码是否匹配已存哈希。"""
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """用 bcrypt 哈希明文密码。"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class VocabularyWord(UUIDModel, table=True):
    """生词库条目，含 SM-2 间隔重复算法状态。

    (user_id, word) 加数据库唯一约束作为兜底；应用层在写入前已用大小写不敏感
    去重（见 app/services/vocabulary/words.py），因此约束按原始大小写比较即可。
    """

    __tablename__ = "vocabulary_words"
    __table_args__ = (UniqueConstraint("user_id", "word", name="uq_vocabulary_word_user_word"),)

    user_id: uuid.UUID = Field(..., foreign_key="vocabulary_users.id", index=True)
    word: str = Field(..., max_length=100, index=True)
    phonetic_ipa: str = Field(..., max_length=100)
    part_of_speech: str = Field(..., max_length=20)
    definition_zh: str = Field(..., max_length=500)

    # new：从未标记为「认识」过；fuzzy：标记过认识但复习间隔还不够长；known：间隔达标
    status: str = Field(default="new", max_length=10, index=True)

    repetition_count: int = Field(default=0)
    easiness_factor: float = Field(default=2.5)
    interval_days: int = Field(default=0)
    next_review_at: datetime
    last_reviewed_at: datetime | None = Field(default=None)


class VocabularyReviewLog(UUIDModel, table=True):
    """每次复习的历史记录，用于统计和排查 SM-2 算法问题。"""

    __tablename__ = "vocabulary_review_logs"

    word_id: uuid.UUID = Field(..., foreign_key="vocabulary_words.id", index=True)
    rating: int = Field(...)  # 0=不认识 1=模糊 2=认识
    reviewed_at: datetime
    interval_before: int
    interval_after: int
