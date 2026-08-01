# app/models/vocabulary.py
"""背单词 App（WordLens）数据模型：独立账户体系 + 生词库 + 复习日志。

WordLens 是与主站投研平台完全独立的产品线，因此 VocabularyUser 不复用
app/models/user.py 的 User 表，账户体系完全隔离。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import bcrypt
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


def _naive_utc_now() -> datetime:
    """返回不带时区的 UTC 当前时间，匹配 naive 的 TIMESTAMP 列类型。

    UUIDModel 的 created_at/updated_at 默认用带时区的 datetime，但这几张表的列是
    TIMESTAMP WITHOUT TIME ZONE：同步驱动 psycopg2 会静默丢弃 tzinfo，asyncpg 不会，
    写入时直接报 DataError。这里覆盖成 naive UTC，和列类型对齐。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class _NaiveTimestampModel(UUIDModel):
    """WordLens 三张表的公共基类：created_at/updated_at 用 naive UTC 覆盖 UUIDModel 默认值。"""

    created_at: datetime = Field(default_factory=_naive_utc_now, nullable=False)
    updated_at: datetime = Field(
        default_factory=_naive_utc_now,
        nullable=False,
        sa_column_kwargs={"onupdate": _naive_utc_now},
    )


class VocabularyUser(_NaiveTimestampModel, table=True):
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


class VocabularyWord(_NaiveTimestampModel, table=True):
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
    etymology: str = Field(default="", max_length=500)
    example_sentence: str = Field(default="", max_length=1000)

    # new：从未标记为「认识」过；fuzzy：标记过认识但复习间隔还不够长；known：间隔达标
    status: str = Field(default="new", max_length=10, index=True)

    repetition_count: int = Field(default=0)
    easiness_factor: float = Field(default=2.5)
    interval_days: int = Field(default=0)
    next_review_at: datetime
    last_reviewed_at: datetime | None = Field(default=None)


class VocabularyReviewLog(_NaiveTimestampModel, table=True):
    """每次复习的历史记录，用于统计和排查 SM-2 算法问题。"""

    __tablename__ = "vocabulary_review_logs"

    word_id: uuid.UUID = Field(..., foreign_key="vocabulary_words.id", index=True)
    rating: int = Field(...)  # 0=不认识 1=模糊 2=认识
    reviewed_at: datetime
    interval_before: int
    interval_after: int


class VocabularyPlaylist(_NaiveTimestampModel, table=True):
    """用户自定义的单词播放列表（「歌单」）。

    首页复习卡的自动播放不再只能播「今日待复习」队列：内置分组（待复习 / 不认识 /
    模糊 / 认识）由既有查询直接算出来，不落库；只有用户手挑单词攒出来的歌单需要
    持久化，就是这张表。歌单名在单个用户下唯一，避免出现两个同名歌单分不清。
    """

    __tablename__ = "vocabulary_playlists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_vocabulary_playlist_user_name"),)

    user_id: uuid.UUID = Field(..., foreign_key="vocabulary_users.id", index=True)
    name: str = Field(..., max_length=50)


class VocabularyPlaylistItem(_NaiveTimestampModel, table=True):
    """歌单与单词的关联，position 保存用户在歌单里的手动顺序。

    (playlist_id, word_id) 唯一：同一个词在一个歌单里只该出现一次。position 从 0
    起连续递增，整体替换词表时按传入数组的下标重写，读取时按它排序。
    """

    __tablename__ = "vocabulary_playlist_items"
    __table_args__ = (UniqueConstraint("playlist_id", "word_id", name="uq_vocabulary_playlist_item"),)

    playlist_id: uuid.UUID = Field(..., foreign_key="vocabulary_playlists.id", index=True)
    word_id: uuid.UUID = Field(..., foreign_key="vocabulary_words.id", index=True)
    position: int = Field(default=0)
