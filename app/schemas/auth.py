"""This file contains the authentication schema for the application."""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

from app.schemas.base import BaseResponse


class Token(BaseModel):
    """Token model for authentication.

    Attributes:
        access_token: The JWT access token.
        token_type: The type of token (always "bearer").
        expires_at: The token expiration timestamp.
    """

    access_token: str = Field(..., description="The JWT access token")
    token_type: str = Field(default="bearer", description="The type of token")
    expires_at: datetime = Field(..., description="The token expiration timestamp")


class TokenResponse(BaseResponse):
    """Response model for login endpoint.

    Attributes:
        access_token: The JWT access token
        token_type: The type of token (always "bearer")
        expires_at: When the token expires
    """

    access_token: str = Field(..., description="The JWT access token")
    token_type: str = Field(default="bearer", description="The type of token")
    expires_at: datetime = Field(..., description="When the token expires")


class UserCreate(BaseModel):
    """Request model for user registration.

    Attributes:
        email: User's email address
        password: User's password
        username: Optional display name
    """

    email: EmailStr = Field(..., description="User's email address")
    password: SecretStr = Field(..., description="User's password", min_length=8, max_length=64)
    username: str | None = Field(default=None, description="Optional display name", max_length=50)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        """Validate password strength.

        Args:
            v: The password to validate

        Returns:
            SecretStr: The validated password

        Raises:
            ValueError: If the password is not strong enough
        """
        # 委托给唯一实现，不在这里复制规则——曾经三处各写一份，
        # 改一处会漏另外两处。
        #
        # 延迟导入：app.utils 的 __init__ 会拉起 app.utils.graph，后者反过来
        # 依赖 app.schemas，模块级导入会成环。
        from app.utils.sanitization import validate_password_strength

        validate_password_strength(v.get_secret_value())
        return v


class UserUpdate(BaseModel):
    """Request model for updating user profile."""

    username: str | None = Field(default=None, description="New username", max_length=50)


class AppleLoginRequest(BaseModel):
    """Sign in with Apple 登录请求。.

    Attributes:
        identity_token: iOS 端返回的 Apple 身份令牌（JWT）。
        full_name: 首次登录时 Apple 提供的姓名（后续为空），用作用户名。
    """

    identity_token: str = Field(..., description="Apple identity token (JWT)")
    full_name: str | None = Field(default=None, description="用户姓名（仅首次登录提供）", max_length=100)


class PasswordChange(BaseModel):
    """Request model for changing password."""

    current_password: SecretStr = Field(..., description="Current password")
    new_password: SecretStr = Field(..., description="New password", min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: SecretStr) -> SecretStr:
        """Validate new password strength.

        Args:
            v: The new password to validate

        Returns:
            SecretStr: The validated password

        Raises:
            ValueError: If the password is not strong enough
        """
        # 委托给唯一实现，不在这里复制规则——曾经三处各写一份，
        # 改一处会漏另外两处。
        #
        # 延迟导入：app.utils 的 __init__ 会拉起 app.utils.graph，后者反过来
        # 依赖 app.schemas，模块级导入会成环。
        from app.utils.sanitization import validate_password_strength

        validate_password_strength(v.get_secret_value())
        return v


class UserProfileResponse(BaseResponse):
    """Response model for user profile."""

    id: int = Field(..., description="User's ID")
    # email 与 phone 都可空：手机号注册的用户没有邮箱，反之亦然。
    email: str | None = Field(default=None, description="User's email address")
    phone: str | None = Field(default=None, description="User's phone in E.164")
    username: str | None = Field(default=None, description="User's display name")
    created_at: datetime = Field(..., description="Account creation timestamp")


class UserResponse(BaseResponse):
    """Response model for user operations.

    Attributes:
        id: User's ID
        email: User's email address
        username: Optional display name
        token: Authentication token
    """

    id: int = Field(..., description="User's ID")
    email: str | None = Field(default=None, description="User's email address")
    phone: str | None = Field(default=None, description="User's phone in E.164")
    username: str | None = Field(default=None, description="Optional display name")
    token: Token = Field(..., description="Authentication token")


class SessionResponse(BaseResponse):
    """Response model for session creation.

    Attributes:
        session_id: The unique identifier for the chat session
        name: Name of the session (defaults to empty string)
        token: The authentication token for the session
    """

    session_id: str = Field(..., description="The unique identifier for the chat session")
    name: str = Field(default="", description="Name of the session", max_length=100)
    token: Token = Field(..., description="The authentication token for the session")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Sanitize the session name.

        Args:
            v: The name to sanitize

        Returns:
            str: The sanitized name
        """
        # Remove any potentially harmful characters
        sanitized = re.sub(r'[<>{}[\]()\'"`]', "", v)
        return sanitized


# ---------------------------------------------------------------------------
# 双通道注册/登录/找回密码
#
# 密码下限跟随主站既有的 validate_password_strength（8–64 位，含字母和数字），
# 比 WordLens 那套 6 位下限严格，不要照抄 vocabulary 的 min_length。
# ---------------------------------------------------------------------------


class EmailCodeRequest(BaseModel):
    """Request a verification code by email (registration or password reset)."""

    email: EmailStr


class EmailRegisterRequest(BaseModel):
    """Register with email and verification code."""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: SecretStr = Field(..., min_length=8, max_length=64)
    username: str | None = Field(default=None, max_length=50)


class EmailPasswordResetConfirm(BaseModel):
    """Reset the password with an email verification code."""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: SecretStr = Field(..., min_length=8, max_length=64)


class PhoneCodeRequest(BaseModel):
    """Request a verification code by SMS.

    号码在服务端归一化，前端不必自己处理格式。
    """

    phone: str = Field(..., min_length=6, max_length=24)


class PhoneRegisterRequest(BaseModel):
    """Register with phone number and verification code."""

    phone: str = Field(..., min_length=6, max_length=24)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: SecretStr = Field(..., min_length=8, max_length=64)
    username: str | None = Field(default=None, max_length=50)


class PhonePasswordResetConfirm(BaseModel):
    """Reset the password with an SMS verification code."""

    phone: str = Field(..., min_length=6, max_length=24)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: SecretStr = Field(..., min_length=8, max_length=64)


class AccountLoginRequest(BaseModel):
    """Unified login.

    account 可以是手机号或邮箱，由服务端判别。
    """

    account: str = Field(..., min_length=3, max_length=255)
    password: SecretStr
