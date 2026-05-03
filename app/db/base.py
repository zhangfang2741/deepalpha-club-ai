# app/db/base.py
"""新模型的 UUID 主键基础类。现有 User/Session 模型继续使用 app/models/base.py。"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class UUIDModel(SQLModel):
    """带 UUID 主键、创建时间、更新时间的公共基础模型。

    所有新 SQLModel 表模型应继承此类（而非 app/models/base.BaseModel）。

    示例：
        class Article(UUIDModel, table=True):
            title: str
            content: str
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
