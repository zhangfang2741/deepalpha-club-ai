"""APNs 设备 token：一个用户可多设备；locale 决定推送语言。"""

from typing import Optional

from sqlmodel import Field

from app.db.base import UUIDModel


class DeviceToken(UUIDModel, table=True):
    """用户的 APNs 设备 token（一个用户可绑定多台设备）。"""

    __tablename__ = "device_token"

    user_id: int = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True, unique=True, description="APNs hex device token")
    platform: str = Field(default="ios")
    locale: str = Field(default="zh-Hans", description="zh-Hans / en")
    last_user_id: Optional[int] = None
