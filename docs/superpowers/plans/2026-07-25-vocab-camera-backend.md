# 拍照背单词后端（Vocabulary Backend）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `deepalpha-club-ai` FastAPI 服务里新增一个独立业务域 `vocabulary`，为拍照背单词 iOS App（WordLens）提供后端支撑：独立账户体系、拍照识别、生词库 CRUD、SM-2 间隔重复复习。

**Architecture:** 遵循项目既有分层规则新增 `app/models/vocabulary.py`（3 张 UUID 主键表）→ `app/services/vocabulary/`（SM-2 算法、LLM 识别、生词 CRUD、账号 CRUD）→ `app/schemas/vocabulary.py`（Pydantic）→ `app/api/v1/vocabulary/`（独立注册登录 + 拍照识别 + 生词库 + 复习端点），挂载到现有 FastAPI 进程的 `/api/v1/vocabulary/*`。

**Tech Stack:** FastAPI + SQLModel + asyncpg（异步端点用 `get_db()`）+ Alembic 迁移 + `llm_service.call()`（复用现有多供应商 LLM 封装，做图片识别）+ pytest（`asyncio_mode=auto`）。

**依赖：** 这是「拍照背单词 iOS App」两个子计划中的第一个（后端）。iOS 端计划（消费本计划产出的 API）是独立的后续计划，本计划产出的 API 契约就是它的输入。

设计依据：[docs/superpowers/specs/2026-07-25-vocab-camera-ios-design.md](../specs/2026-07-25-vocab-camera-ios-design.md)

---

## 文件结构总览

```
app/models/vocabulary.py                     # VocabularyUser / VocabularyWord / VocabularyReviewLog
app/schemas/vocabulary.py                    # 所有请求/响应 Pydantic schema
app/services/vocabulary/__init__.py          # 空模块初始化
app/services/vocabulary/sm2.py               # SM-2 间隔重复算法（纯函数）
app/services/vocabulary/recognizer.py        # LLM 拍照识别单词
app/services/vocabulary/users.py             # VocabularyUser 账号 DB 操作
app/services/vocabulary/words.py             # 生词库 CRUD + 去重 + 复习提交
app/api/v1/vocabulary/__init__.py            # 路由汇总
app/api/v1/vocabulary/dependencies.py        # get_current_vocab_user 鉴权依赖
app/api/v1/vocabulary/auth.py                # 注册/登录路由
app/api/v1/vocabulary/words.py               # 识别/生词库/复习路由
app/api/v1/api.py                            # [修改] 挂载 vocabulary 路由
alembic/versions/<autogen>.py                # [生成] 新表迁移
tests/services/vocabulary/__init__.py
tests/services/vocabulary/test_sm2.py
tests/services/vocabulary/test_recognizer.py
tests/services/vocabulary/test_words.py
```

---

### Task 1: 数据模型 + Alembic 迁移

**Files:**
- Create: `app/models/vocabulary.py`
- Create (autogen): `alembic/versions/<hash>_add_vocabulary_tables.py`

- [ ] **Step 1: 创建数据模型文件**

```python
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
```

- [ ] **Step 2: 生成迁移**

Run: `make migration MSG="add vocabulary tables"`

Expected: 在 `alembic/versions/` 下生成一个新文件，内容包含 `create_table('vocabulary_users', ...)`、`create_table('vocabulary_words', ...)`、`create_table('vocabulary_review_logs', ...)`，以及 `uq_vocabulary_word_user_word` 唯一约束和三张表的外键。

- [ ] **Step 3: 检查生成的迁移文件**

打开生成的文件，确认：
- 三张表都有 `id`(UUID, primary key)、`created_at`、`updated_at`
- `vocabulary_words.user_id` 外键指向 `vocabulary_users.id`
- `vocabulary_review_logs.word_id` 外键指向 `vocabulary_words.id`
- `vocabulary_words` 上有 `uq_vocabulary_word_user_word` 唯一约束

如果 autogenerate 漏掉了某个外键或约束（偶尔发生），手动补全对应的 `op.create_foreign_key` / `op.create_unique_constraint` 调用。

- [ ] **Step 4: 应用迁移**

Run: `make migrate`

Expected: 无报错，`alembic_version` 表更新到新版本号。

- [ ] **Step 5: 提交**

```bash
git add app/models/vocabulary.py alembic/versions/
git commit -m "feat(vocabulary): 新增背单词 App 数据模型（用户/生词/复习日志）"
```

---

### Task 2: SM-2 间隔重复算法（TDD）

**Files:**
- Create: `app/services/vocabulary/__init__.py`
- Create: `app/services/vocabulary/sm2.py`
- Test: `tests/services/vocabulary/__init__.py`
- Test: `tests/services/vocabulary/test_sm2.py`

- [ ] **Step 1: 创建空的服务包初始化文件**

```python
# app/services/vocabulary/__init__.py
```

```python
# tests/services/vocabulary/__init__.py
```

- [ ] **Step 2: 写 SM-2 算法的 failing test**

```python
# tests/services/vocabulary/test_sm2.py
"""SM-2 间隔重复算法单元测试。"""
import datetime

import pytest

from app.services.vocabulary.sm2 import MIN_EASINESS_FACTOR, apply_review

FIXED_NOW = datetime.datetime(2026, 7, 25, 12, 0, 0, tzinfo=datetime.UTC)


def test_unknown_rating_resets_repetition_and_short_interval():
    result = apply_review(rating=0, repetition_count=5, easiness_factor=2.6, interval_days=30, now=FIXED_NOW)
    assert result.repetition_count == 0
    assert result.interval_days == 1
    assert result.status == "new"
    assert result.next_review_at == FIXED_NOW + datetime.timedelta(days=1)


def test_fuzzy_rating_keeps_repetition_short_interval_lowers_ef():
    result = apply_review(rating=1, repetition_count=2, easiness_factor=2.5, interval_days=6, now=FIXED_NOW)
    assert result.repetition_count == 2
    assert result.interval_days == 1
    assert result.easiness_factor == pytest.approx(2.35)
    assert result.status == "fuzzy"


def test_known_rating_first_repetition_sets_interval_to_one_day():
    result = apply_review(rating=2, repetition_count=0, easiness_factor=2.5, interval_days=0, now=FIXED_NOW)
    assert result.repetition_count == 1
    assert result.interval_days == 1
    assert result.easiness_factor == pytest.approx(2.6)
    assert result.status == "fuzzy"  # 未达 21 天阈值


def test_known_rating_second_repetition_sets_interval_to_six_days():
    result = apply_review(rating=2, repetition_count=1, easiness_factor=2.6, interval_days=1, now=FIXED_NOW)
    assert result.repetition_count == 2
    assert result.interval_days == 6
    assert result.status == "fuzzy"


def test_known_rating_third_repetition_multiplies_interval_by_ef():
    result = apply_review(rating=2, repetition_count=2, easiness_factor=2.6, interval_days=6, now=FIXED_NOW)
    assert result.repetition_count == 3
    assert result.easiness_factor == pytest.approx(2.7)
    assert result.interval_days == 16  # round(6 * 2.7) = 16
    assert result.status == "fuzzy"  # 16 天未过 21 天阈值


def test_known_status_reached_when_interval_exceeds_threshold():
    result = apply_review(rating=2, repetition_count=3, easiness_factor=2.7, interval_days=16, now=FIXED_NOW)
    assert result.repetition_count == 4
    assert result.interval_days == 45  # round(16 * 2.8) = 45
    assert result.status == "known"


def test_easiness_factor_never_drops_below_minimum():
    result = apply_review(
        rating=1, repetition_count=0, easiness_factor=MIN_EASINESS_FACTOR, interval_days=1, now=FIXED_NOW
    )
    assert result.easiness_factor == MIN_EASINESS_FACTOR


def test_invalid_rating_raises_value_error():
    with pytest.raises(ValueError):
        apply_review(rating=3, repetition_count=0, easiness_factor=2.5, interval_days=0, now=FIXED_NOW)
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `uv run pytest tests/services/vocabulary/test_sm2.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.services.vocabulary.sm2'`

- [ ] **Step 4: 实现 SM-2 算法**

```python
# app/services/vocabulary/sm2.py
"""SM-2 间隔重复算法：根据复习评分计算下一次复习状态。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MIN_EASINESS_FACTOR = 2.13
FUZZY_INTERVAL_DAYS = 1
UNKNOWN_INTERVAL_DAYS = 1
KNOWN_STATUS_INTERVAL_THRESHOLD_DAYS = 21


@dataclass
class SM2Result:
    """一次复习后的新状态。"""

    repetition_count: int
    easiness_factor: float
    interval_days: int
    next_review_at: datetime
    status: str  # "new" | "fuzzy" | "known"


def apply_review(
    *,
    rating: int,
    repetition_count: int,
    easiness_factor: float,
    interval_days: int,
    now: datetime | None = None,
) -> SM2Result:
    """根据本次评分计算新的 SM-2 状态。

    Args:
        rating: 0（不认识）/ 1（模糊）/ 2（认识）
        repetition_count: 当前连续「认识」次数
        easiness_factor: 当前难度系数
        interval_days: 当前复习间隔（天）
        now: 当前时间，默认取 UTC now（测试可注入固定时间）

    Returns:
        SM2Result: 更新后的状态

    Raises:
        ValueError: rating 不在 0/1/2 范围内
    """
    if rating not in (0, 1, 2):
        raise ValueError(f"invalid rating: {rating}")

    current_time = now or datetime.now(UTC)

    if rating == 0:
        new_repetition = 0
        new_interval = UNKNOWN_INTERVAL_DAYS
        new_ef = easiness_factor
        status = "new"
    elif rating == 1:
        new_repetition = repetition_count
        new_interval = FUZZY_INTERVAL_DAYS
        new_ef = max(MIN_EASINESS_FACTOR, round(easiness_factor - 0.15, 2))
        status = "fuzzy"
    else:  # rating == 2
        new_repetition = repetition_count + 1
        new_ef = max(MIN_EASINESS_FACTOR, round(easiness_factor + 0.1, 2))
        if new_repetition == 1:
            new_interval = 1
        elif new_repetition == 2:
            new_interval = 6
        else:
            new_interval = round(interval_days * new_ef)
        status = "known" if new_interval >= KNOWN_STATUS_INTERVAL_THRESHOLD_DAYS else "fuzzy"

    next_review_at = current_time + timedelta(days=new_interval)

    return SM2Result(
        repetition_count=new_repetition,
        easiness_factor=new_ef,
        interval_days=new_interval,
        next_review_at=next_review_at,
        status=status,
    )
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `uv run pytest tests/services/vocabulary/test_sm2.py -v`
Expected: 8 个测试全部 PASS

- [ ] **Step 6: 提交**

```bash
git add app/services/vocabulary/__init__.py app/services/vocabulary/sm2.py tests/services/vocabulary/
git commit -m "feat(vocabulary): 实现 SM-2 间隔重复算法"
```

---

### Task 3: 生词去重逻辑（TDD）

**Files:**
- Create: `app/services/vocabulary/words.py`（本任务只写 `filter_new_words`，Task 7 补充 DB 相关函数）
- Test: `tests/services/vocabulary/test_words.py`

- [ ] **Step 1: 写去重逻辑的 failing test**

```python
# tests/services/vocabulary/test_words.py
"""生词库去重逻辑单元测试。"""
from app.services.vocabulary.words import filter_new_words


def test_filter_new_words_excludes_existing_case_insensitive():
    existing = {"Apple", "Resilient"}
    candidates = ["apple", "Paradigm", "RESILIENT", "banana"]
    result = filter_new_words(existing, candidates)
    assert result == ["Paradigm", "banana"]


def test_filter_new_words_dedupes_within_candidates():
    existing: set[str] = set()
    candidates = ["apple", "Apple", "APPLE", "banana"]
    result = filter_new_words(existing, candidates)
    assert result == ["apple", "banana"]


def test_filter_new_words_returns_empty_when_all_exist():
    existing = {"apple", "banana"}
    candidates = ["Apple", "BANANA"]
    result = filter_new_words(existing, candidates)
    assert result == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/services/vocabulary/test_words.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.services.vocabulary.words'`

- [ ] **Step 3: 实现 `filter_new_words`**

```python
# app/services/vocabulary/words.py
"""生词库 CRUD 与去重逻辑。"""
from __future__ import annotations


def filter_new_words(existing_words: set[str], candidates: list[str]) -> list[str]:
    """过滤掉已在生词库中的候选词（大小写不敏感），保留候选词原始大小写与顺序。

    Args:
        existing_words: 生词库中已存在的单词（原始大小写，内部转小写比较）
        candidates: 候选词列表（原始大小写）

    Returns:
        candidates 中尚未加入生词库的词，内部按小写去重，保留第一次出现的大小写
    """
    existing_lower = {w.lower() for w in existing_words}
    result: list[str] = []
    seen_lower: set[str] = set()
    for word in candidates:
        lower = word.lower()
        if lower in existing_lower or lower in seen_lower:
            continue
        seen_lower.add(lower)
        result.append(word)
    return result
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/services/vocabulary/test_words.py -v`
Expected: 3 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/vocabulary/words.py tests/services/vocabulary/test_words.py
git commit -m "feat(vocabulary): 实现生词库大小写不敏感去重逻辑"
```

---

### Task 4: LLM 拍照识别服务（TDD）

**Files:**
- Create: `app/services/vocabulary/recognizer.py`
- Test: `tests/services/vocabulary/test_recognizer.py`

- [ ] **Step 1: 写识别服务的 failing test**

```python
# tests/services/vocabulary/test_recognizer.py
"""LLM 拍照识别单词服务单元测试（mock llm_service.call，不触网）。"""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.vocabulary.recognizer import (
    RecognitionFailedError,
    RecognizedWord,
    _RecognizeResult,
    recognize_words_from_image,
)


async def test_recognize_words_returns_parsed_candidates():
    mock_result = _RecognizeResult(
        words=[
            RecognizedWord(
                word="resilient",
                phonetic_ipa="rɪˈzɪliənt",
                part_of_speech="adj.",
                definition_zh="有韧性的",
            )
        ]
    )
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(return_value=mock_result),
    ):
        words = await recognize_words_from_image(b"fake-image-bytes")

    assert len(words) == 1
    assert words[0].word == "resilient"
    assert words[0].phonetic_ipa == "rɪˈzɪliənt"
    assert words[0].part_of_speech == "adj."


async def test_recognize_words_returns_empty_list_when_no_words_found():
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(return_value=_RecognizeResult(words=[])),
    ):
        words = await recognize_words_from_image(b"fake-image-bytes")

    assert words == []


async def test_recognize_words_raises_on_llm_failure():
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(side_effect=RuntimeError("llm down")),
    ):
        with pytest.raises(RecognitionFailedError):
            await recognize_words_from_image(b"fake-image-bytes")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/services/vocabulary/test_recognizer.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.services.vocabulary.recognizer'`

- [ ] **Step 3: 实现识别服务**

```python
# app/services/vocabulary/recognizer.py
"""拍照识别英语单词：调用 LLM 做图片 OCR + 音标 + 释义生成。"""
from __future__ import annotations

import base64

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.llm.service import llm_service

_RECOGNIZE_PROMPT = (
    "你是一个英语学习助手。请识别这张图片中出现的所有英语单词（排除纯虚词，如冠词 "
    "a/an/the、介词、连词），为每个单词提供：国际音标（IPA，不含斜杠）、词性缩写"
    "（如 n./v./adj./adv.）、简洁的中文释义。如果图片中没有可识别的英语单词，返回空列表。"
)


class RecognizedWord(BaseModel):
    """单个识别出的单词。"""

    word: str = Field(..., description="识别出的英语单词原形")
    phonetic_ipa: str = Field(..., description="国际音标，不含斜杠")
    part_of_speech: str = Field(..., description="词性缩写")
    definition_zh: str = Field(..., description="简洁中文释义")


class _RecognizeResult(BaseModel):
    """LLM 结构化输出的顶层容器。"""

    words: list[RecognizedWord] = Field(default_factory=list)


class RecognitionFailedError(Exception):
    """图片识别失败（LLM 调用异常）。"""


async def recognize_words_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> list[RecognizedWord]:
    """调用 LLM 识别图片中的英语单词，返回候选词列表。

    Args:
        image_bytes: 图片原始字节
        mime_type: 图片 MIME 类型

    Returns:
        识别出的候选单词列表（可能为空）

    Raises:
        RecognitionFailedError: LLM 调用失败
    """
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    message = HumanMessage(
        content=[
            {"type": "text", "text": _RECOGNIZE_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
        ]
    )
    try:
        result = await llm_service.call([message], response_format=_RecognizeResult)
    except Exception as exc:
        logger.exception("vocabulary_recognize_llm_call_failed")
        raise RecognitionFailedError("LLM 识别调用失败") from exc

    logger.info("vocabulary_recognize_succeeded", word_count=len(result.words))
    return result.words
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/services/vocabulary/test_recognizer.py -v`
Expected: 3 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/vocabulary/recognizer.py tests/services/vocabulary/test_recognizer.py
git commit -m "feat(vocabulary): 实现 LLM 拍照识别单词服务"
```

---

### Task 5: Pydantic Schemas

**Files:**
- Create: `app/schemas/vocabulary.py`

- [ ] **Step 1: 创建 schema 文件**

```python
# app/schemas/vocabulary.py
"""背单词 App（WordLens）请求/响应 schema。"""
from __future__ import annotations

import uuid
from datetime import datetime

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


class RecognizedWordSchema(BaseModel):
    """识别出的单个候选词。"""

    word: str
    phonetic_ipa: str
    part_of_speech: str
    definition_zh: str
    already_in_library: bool = False


class RecognizeResponse(BaseResponse):
    """拍照识别响应。"""

    candidates: list[RecognizedWordSchema]


class VocabularyWordCreate(BaseModel):
    """批量加入生词库时的单个词。"""

    word: str = Field(..., max_length=100)
    phonetic_ipa: str = Field(..., max_length=100)
    part_of_speech: str = Field(..., max_length=20)
    definition_zh: str = Field(..., max_length=500)


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
```

- [ ] **Step 2: 语法检查**

Run: `uv run python -c "import app.schemas.vocabulary"`
Expected: 无报错（无输出即成功）

- [ ] **Step 3: 提交**

```bash
git add app/schemas/vocabulary.py
git commit -m "feat(vocabulary): 新增背单词 App 请求响应 schema"
```

---

### Task 6: 账号 DB 操作 + 独立注册登录路由

**Files:**
- Create: `app/services/vocabulary/users.py`
- Create: `app/api/v1/vocabulary/__init__.py`
- Create: `app/api/v1/vocabulary/dependencies.py`
- Create: `app/api/v1/vocabulary/auth.py`

- [ ] **Step 1: 实现账号 DB 操作**

```python
# app/services/vocabulary/users.py
"""VocabularyUser 账号 DB 操作。"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vocabulary import VocabularyUser


async def get_user_by_email(session: AsyncSession, email: str) -> VocabularyUser | None:
    """按邮箱查找用户。"""
    stmt = select(VocabularyUser).where(VocabularyUser.email == email)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> VocabularyUser | None:
    """按 id 查找用户。"""
    return await session.get(VocabularyUser, user_id)


async def create_user(session: AsyncSession, email: str, hashed_password: str) -> VocabularyUser:
    """创建新用户。"""
    user = VocabularyUser(email=email, hashed_password=hashed_password)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
```

- [ ] **Step 2: 创建鉴权依赖**

```python
# app/api/v1/vocabulary/dependencies.py
"""WordLens 独立账户体系的鉴权依赖。"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.services.vocabulary import users as user_service
from app.utils.auth import verify_token
from app.utils.sanitization import sanitize_string

security = HTTPBearer()


async def get_current_vocab_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> VocabularyUser:
    """从 JWT 解析并返回当前 WordLens 用户。"""
    token = sanitize_string(credentials.credentials)
    raw_user_id = verify_token(token)
    if raw_user_id is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid token format") from exc

    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

- [ ] **Step 3: 创建注册/登录路由**

```python
# app/api/v1/vocabulary/auth.py
"""WordLens 独立注册/登录路由（不复用主站 /auth）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    VocabularyLoginRequest,
    VocabularyTokenResponse,
    VocabularyUserCreate,
)
from app.services.vocabulary import users as user_service
from app.utils.auth import create_access_token
from app.utils.sanitization import sanitize_email, validate_password_strength

router = APIRouter()


@router.post("/register", response_model=VocabularyTokenResponse)
async def register(payload: VocabularyUserCreate, db: AsyncSession = Depends(get_db)):
    """注册新 WordLens 账号。"""
    email = sanitize_email(payload.email)
    password = payload.password.get_secret_value()
    validate_password_strength(password)

    existing = await user_service.get_user_by_email(db, email)
    if existing is not None:
        raise HTTPException(status_code=400, detail="该邮箱已被注册")

    hashed = VocabularyUser.hash_password(password)
    user = await user_service.create_user(db, email, hashed)
    token = create_access_token(str(user.id))
    logger.info("vocabulary_user_registered", user_id=str(user.id))
    return VocabularyTokenResponse(access_token=token.access_token, expires_at=token.expires_at)


@router.post("/login", response_model=VocabularyTokenResponse)
async def login(payload: VocabularyLoginRequest, db: AsyncSession = Depends(get_db)):
    """WordLens 账号登录。"""
    email = sanitize_email(payload.email)
    user = await user_service.get_user_by_email(db, email)
    if user is None or not user.verify_password(payload.password.get_secret_value()):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(str(user.id))
    logger.info("vocabulary_user_logged_in", user_id=str(user.id))
    return VocabularyTokenResponse(access_token=token.access_token, expires_at=token.expires_at)
```

- [ ] **Step 4: 创建路由汇总（先只挂 auth，Task 8 补充 words）**

```python
# app/api/v1/vocabulary/__init__.py
"""WordLens 拍照背单词模块路由汇总。"""
from fastapi import APIRouter

from .auth import router as auth_router

router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["vocabulary-auth"])
```

- [ ] **Step 5: 语法检查**

Run: `uv run python -c "import app.api.v1.vocabulary"`
Expected: 无报错

- [ ] **Step 6: 提交**

```bash
git add app/services/vocabulary/users.py app/api/v1/vocabulary/
git commit -m "feat(vocabulary): 新增独立账户注册登录路由"
```

---

### Task 7: 生词库 CRUD + 复习提交服务

**Files:**
- Modify: `app/services/vocabulary/words.py`（在 Task 3 的 `filter_new_words` 基础上追加 DB 操作函数）

- [ ] **Step 1: 用完整文件内容替换 `app/services/vocabulary/words.py`**

这一步是把 Task 3 已有的 `filter_new_words` 和新增的 DB 操作函数合并进同一个文件。用下面的完整内容**整体替换** `app/services/vocabulary/words.py`（不是追加）：

```python
# app/services/vocabulary/words.py
"""生词库 CRUD 与去重逻辑。"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vocabulary import VocabularyReviewLog, VocabularyWord
from app.services.vocabulary import sm2


def filter_new_words(existing_words: set[str], candidates: list[str]) -> list[str]:
    """过滤掉已在生词库中的候选词（大小写不敏感），保留候选词原始大小写与顺序。

    Args:
        existing_words: 生词库中已存在的单词（原始大小写，内部转小写比较）
        candidates: 候选词列表（原始大小写）

    Returns:
        candidates 中尚未加入生词库的词，内部按小写去重，保留第一次出现的大小写
    """
    existing_lower = {w.lower() for w in existing_words}
    result: list[str] = []
    seen_lower: set[str] = set()
    for word in candidates:
        lower = word.lower()
        if lower in existing_lower or lower in seen_lower:
            continue
        seen_lower.add(lower)
        result.append(word)
    return result


async def get_existing_words(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """返回某用户生词库中所有单词（原始大小写）。"""
    stmt = select(VocabularyWord.word).where(VocabularyWord.user_id == user_id)
    res = await session.execute(stmt)
    return set(res.scalars().all())


async def create_words_batch(
    session: AsyncSession, user_id: uuid.UUID, words: list[dict]
) -> list[VocabularyWord]:
    """批量插入生词（调用方已去重）。"""
    now = datetime.datetime.now(datetime.UTC)
    rows = [
        VocabularyWord(
            user_id=user_id,
            word=w["word"],
            phonetic_ipa=w["phonetic_ipa"],
            part_of_speech=w["part_of_speech"],
            definition_zh=w["definition_zh"],
            status="new",
            next_review_at=now,
        )
        for w in words
    ]
    session.add_all(rows)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


async def add_words_with_dedup(
    session: AsyncSession, user_id: uuid.UUID, words: list[dict]
) -> tuple[list[VocabularyWord], list[str]]:
    """批量加入生词库并自动去重。

    Returns:
        (新建的单词行, 被跳过的重复词原文)
    """
    existing = await get_existing_words(session, user_id)
    existing_lower = {w.lower() for w in existing}
    seen_lower: set[str] = set()
    to_create: list[dict] = []
    skipped: list[str] = []
    for w in words:
        lower = w["word"].lower()
        if lower in existing_lower or lower in seen_lower:
            skipped.append(w["word"])
            continue
        seen_lower.add(lower)
        to_create.append(w)
    created = await create_words_batch(session, user_id, to_create)
    return created, skipped


async def list_words(
    session: AsyncSession, user_id: uuid.UUID, status: str | None = None, query: str | None = None
) -> list[VocabularyWord]:
    """生词库列表，支持按状态筛选和关键词搜索。"""
    stmt = select(VocabularyWord).where(VocabularyWord.user_id == user_id)
    if status:
        stmt = stmt.where(VocabularyWord.status == status)
    if query:
        stmt = stmt.where(VocabularyWord.word.ilike(f"%{query}%"))
    stmt = stmt.order_by(VocabularyWord.created_at.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_word(session: AsyncSession, user_id: uuid.UUID, word_id: uuid.UUID) -> VocabularyWord | None:
    """按 id 获取单词详情（校验属于该用户）。"""
    stmt = select(VocabularyWord).where(VocabularyWord.id == word_id, VocabularyWord.user_id == user_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def delete_word(session: AsyncSession, user_id: uuid.UUID, word_id: uuid.UUID) -> bool:
    """删除单词，成功返回 True，不存在返回 False。"""
    word = await get_word(session, user_id, word_id)
    if word is None:
        return False
    await session.delete(word)
    await session.commit()
    return True


async def get_review_queue(session: AsyncSession, user_id: uuid.UUID) -> list[VocabularyWord]:
    """待复习队列：next_review_at <= now，按到期时间升序。"""
    now = datetime.datetime.now(datetime.UTC)
    stmt = (
        select(VocabularyWord)
        .where(VocabularyWord.user_id == user_id, VocabularyWord.next_review_at <= now)
        .order_by(VocabularyWord.next_review_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def submit_review(
    session: AsyncSession, user_id: uuid.UUID, word_id: uuid.UUID, rating: int
) -> VocabularyWord | None:
    """提交一次复习结果：跑 SM-2、更新单词状态、写复习日志。"""
    word = await get_word(session, user_id, word_id)
    if word is None:
        return None

    result = sm2.apply_review(
        rating=rating,
        repetition_count=word.repetition_count,
        easiness_factor=word.easiness_factor,
        interval_days=word.interval_days,
    )
    reviewed_at = datetime.datetime.now(datetime.UTC)
    log = VocabularyReviewLog(
        word_id=word.id,
        rating=rating,
        reviewed_at=reviewed_at,
        interval_before=word.interval_days,
        interval_after=result.interval_days,
    )
    word.repetition_count = result.repetition_count
    word.easiness_factor = result.easiness_factor
    word.interval_days = result.interval_days
    word.next_review_at = result.next_review_at
    word.last_reviewed_at = reviewed_at
    word.status = result.status

    session.add(word)
    session.add(log)
    await session.commit()
    await session.refresh(word)
    return word
```

- [ ] **Step 2: 语法检查**

Run: `uv run python -c "import app.services.vocabulary.words"`
Expected: 无报错

- [ ] **Step 3: 回归测试 Task 3 的去重测试仍然通过**

Run: `uv run pytest tests/services/vocabulary/test_words.py -v`
Expected: 3 个测试全部 PASS（未受新增代码影响）

- [ ] **Step 4: 提交**

```bash
git add app/services/vocabulary/words.py
git commit -m "feat(vocabulary): 实现生词库 CRUD 与复习提交服务"
```

---

### Task 8: 拍照识别 + 生词库 + 复习 API 路由

**Files:**
- Create: `app/api/v1/vocabulary/words.py`
- Modify: `app/api/v1/vocabulary/__init__.py`
- Modify: `app/api/v1/api.py`

- [ ] **Step 1: 创建 words 路由文件**

```python
# app/api/v1/vocabulary/words.py
"""WordLens 拍照识别 + 生词库 + 复习 API。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    RecognizedWordSchema,
    RecognizeResponse,
    ReviewQueueResponse,
    ReviewSubmitRequest,
    ReviewSubmitResponse,
    VocabularyWordListResponse,
    VocabularyWordResponse,
    WordsBatchCreateRequest,
    WordsBatchCreateResponse,
)
from app.services.vocabulary import words as word_service
from app.services.vocabulary.recognizer import RecognitionFailedError, recognize_words_from_image

from .dependencies import get_current_vocab_user

router = APIRouter()


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    image: UploadFile = File(...),
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """上传图片，识别出候选英语单词（不落库、不存图）。"""
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="图片为空")

    try:
        recognized = await recognize_words_from_image(image_bytes, image.content_type or "image/jpeg")
    except RecognitionFailedError as exc:
        raise HTTPException(status_code=502, detail="识别失败，请重新拍摄") from exc

    existing = await word_service.get_existing_words(db, user.id)
    new_words = word_service.filter_new_words(existing, [w.word for w in recognized])
    new_words_lower = {w.lower() for w in new_words}

    candidates = [
        RecognizedWordSchema(
            word=w.word,
            phonetic_ipa=w.phonetic_ipa,
            part_of_speech=w.part_of_speech,
            definition_zh=w.definition_zh,
            already_in_library=w.word.lower() not in new_words_lower,
        )
        for w in recognized
    ]
    return RecognizeResponse(candidates=candidates)


@router.post("/words/batch", response_model=WordsBatchCreateResponse)
async def add_words_batch(
    payload: WordsBatchCreateRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """批量加入生词库，自动按大小写不敏感去重。"""
    created_rows, skipped = await word_service.add_words_with_dedup(
        db, user.id, [w.model_dump() for w in payload.words]
    )
    return WordsBatchCreateResponse(
        created=[VocabularyWordResponse.model_validate(r) for r in created_rows],
        skipped_existing=skipped,
    )


@router.get("/words", response_model=VocabularyWordListResponse)
async def list_words_endpoint(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """生词库列表，支持按状态筛选和关键词搜索。"""
    rows = await word_service.list_words(db, user.id, status=status, query=q)
    return VocabularyWordListResponse(words=[VocabularyWordResponse.model_validate(r) for r in rows])


@router.get("/words/{word_id}", response_model=VocabularyWordResponse)
async def get_word_detail(
    word_id: uuid.UUID,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """单词详情。"""
    word = await word_service.get_word(db, user.id, word_id)
    if word is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    return VocabularyWordResponse.model_validate(word)


@router.delete("/words/{word_id}")
async def delete_word_endpoint(
    word_id: uuid.UUID,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """删除单词。"""
    ok = await word_service.delete_word(db, user.id, word_id)
    if not ok:
        raise HTTPException(status_code=404, detail="单词不存在")
    return {"deleted": True}


@router.get("/review/queue", response_model=ReviewQueueResponse)
async def review_queue(
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """待复习队列。"""
    rows = await word_service.get_review_queue(db, user.id)
    return ReviewQueueResponse(words=[VocabularyWordResponse.model_validate(r) for r in rows])


@router.post("/words/{word_id}/review", response_model=ReviewSubmitResponse)
async def submit_review_endpoint(
    word_id: uuid.UUID,
    payload: ReviewSubmitRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """提交一次复习结果，更新 SM-2 状态。"""
    word = await word_service.submit_review(db, user.id, word_id, payload.rating)
    if word is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    logger.info("vocabulary_review_submitted", word_id=str(word_id), rating=payload.rating)
    return ReviewSubmitResponse(word=VocabularyWordResponse.model_validate(word))
```

- [ ] **Step 2: 把 words 路由挂到汇总路由**

```python
# app/api/v1/vocabulary/__init__.py
"""WordLens 拍照背单词模块路由汇总。"""
from fastapi import APIRouter

from .auth import router as auth_router
from .words import router as words_router

router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["vocabulary-auth"])
router.include_router(words_router, tags=["vocabulary-words"])
```

- [ ] **Step 3: 在 `app/api/v1/api.py` 挂载 vocabulary 路由**

修改 `app/api/v1/api.py:16`，在 `from app.api.v1.valuation import router as valuation_router` 之后插入：

```python
from app.api.v1.vocabulary import router as vocabulary_router
```

修改 `app/api/v1/api.py` 中 `api_router.include_router(valuation_router, ...)` 之后插入：

```python
api_router.include_router(vocabulary_router, prefix="/vocabulary", tags=["vocabulary"])
```

- [ ] **Step 4: 语法检查 + 启动服务确认路由注册成功**

Run: `uv run python -c "from app.main import app; print([r.path for r in app.routes if 'vocabulary' in r.path])"`
Expected: 打印出包含 `/api/v1/vocabulary/auth/register`、`/api/v1/vocabulary/auth/login`、`/api/v1/vocabulary/recognize`、`/api/v1/vocabulary/words`、`/api/v1/vocabulary/words/{word_id}`、`/api/v1/vocabulary/words/batch`、`/api/v1/vocabulary/words/{word_id}/review`、`/api/v1/vocabulary/review/queue` 的路径列表

- [ ] **Step 5: 提交**

```bash
git add app/api/v1/vocabulary/words.py app/api/v1/vocabulary/__init__.py app/api/v1/api.py
git commit -m "feat(vocabulary): 新增拍照识别/生词库/复习 API 路由"
```

---

### Task 9: 端到端手动验证

**Files:** 无代码改动，仅验证

- [ ] **Step 1: 跑一遍全量测试确认无回归**

Run: `uv run pytest tests/services/vocabulary/ -v`
Expected: 全部 PASS（Task 2/3/4 的测试，共 14 个）

Run: `make check`
Expected: `ruff check .` 和 `pyright` 均无新增报错（新文件需符合项目 lint 规则）

- [ ] **Step 2: 本地起服务**

Run: `make dev`
Expected: uvicorn 在 `:8000` 启动成功，无导入错误

- [ ] **Step 3: 手动跑通注册 → 登录 → 生词库全流程**

```bash
# 注册
curl -s -X POST http://localhost:8000/api/v1/vocabulary/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!"}' | tee /tmp/register.json

TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/register.json'))['access_token'])")

# 手动加入两个生词（跳过识别，直接测 CRUD）
curl -s -X POST http://localhost:8000/api/v1/vocabulary/words/batch \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"words":[{"word":"resilient","phonetic_ipa":"rɪˈzɪliənt","part_of_speech":"adj.","definition_zh":"有韧性的"}]}'

# 列表
curl -s http://localhost:8000/api/v1/vocabulary/words -H "Authorization: Bearer $TOKEN"

# 待复习队列（刚加入的词应立即到期）
curl -s http://localhost:8000/api/v1/vocabulary/review/queue -H "Authorization: Bearer $TOKEN"

# 提交复习（rating=2 认识）
WORD_ID=$(curl -s http://localhost:8000/api/v1/vocabulary/words -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys;print(json.load(sys.stdin)['words'][0]['id'])")
curl -s -X POST http://localhost:8000/api/v1/vocabulary/words/$WORD_ID/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"rating":2}'
```

Expected: 每一步都返回 200 且 JSON 结构符合 Task 5 定义的 schema；复习提交后返回的 `word.next_review_at` 应比当前时间晚 1 天左右，`word.repetition_count == 1`。

- [ ] **Step 4: 清理测试数据（可选）**

如果不想保留手动测试产生的账号，直接用 `psql` 删除 `vocabulary_users` 表里 email 为 `test@example.com` 的行（级联删除其生词与复习记录，需先确认外键是否设置了 `ON DELETE CASCADE`；若没有，先手动删 `vocabulary_words`/`vocabulary_review_logs` 里对应的行）。个人自用工具场景下也可以不清理，直接保留作为真实第一个账号。

---

## 后续（本计划不含，留给 iOS 端计划）

- iOS 端 `ios/WordLens` 工程消费本计划产出的全部 8 个 API 端点
- `recognize` 接口需要真实图片实测识别准确率，必要时回头调整 prompt（`app/services/vocabulary/recognizer.py` 里的 `_RECOGNIZE_PROMPT`）
