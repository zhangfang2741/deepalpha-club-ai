"""This file contains the user model for the application."""

from datetime import datetime
from typing import (
    TYPE_CHECKING,
    List,
    Optional,
)

import bcrypt
from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class User(BaseModel, table=True):
    """User model for storing user accounts.

    Attributes:
        id: The primary key
        email: User's email (可空唯一；手机号注册的用户没有邮箱)
        phone: E.164 格式手机号（可空唯一；邮箱注册的用户没有手机号）
        hashed_password: Bcrypt hashed password
        username: Optional display name for the user
        created_at: When the user was created
        sessions: Relationship to user's chat sessions
    """

    id: int = Field(default=None, primary_key=True)
    # email 与 phone 都可空，但应用层保证至少有一个：手机号注册的用户没有邮箱，
    # 反之亦然。Postgres 的 unique 约束允许多行 NULL，两列同时可空唯一是安全的。
    email: Optional[str] = Field(default=None, unique=True, index=True)
    phone: Optional[str] = Field(default=None, unique=True, index=True, max_length=20)
    hashed_password: str
    username: Optional[str] = Field(default=None, index=False)
    # 用户偏好的 LLM 模型名（须为当前 provider 已注册的模型名）；为空则用系统默认。
    preferred_model: Optional[str] = Field(default=None, index=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sessions: List["Session"] = Relationship(back_populates="user")

    def verify_password(self, password: str) -> bool:
        """Verify if the provided password matches the hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# Avoid circular imports
from app.models.session import Session  # noqa: E402
