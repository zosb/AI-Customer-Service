from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    """邮箱或手机号注册请求。"""

    account: str = Field(
        min_length=3,
        max_length=255,
        description="邮箱地址或手机号",
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="登录密码",
    )
    display_name: str | None = Field(
        default=None,
        max_length=64,
        description="显示名称",
    )

    @field_validator("account")
    @classmethod
    def strip_account(cls, value: str) -> str:
        return value.strip()

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class LoginRequest(BaseModel):
    """邮箱或手机号登录请求。"""

    account: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("account")
    @classmethod
    def strip_account(cls, value: str) -> str:
        return value.strip()


class UserPublic(BaseModel):
    """可安全返回给前端的用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    phone: str | None
    display_name: str | None
    role: str
    status: str
    created_at: datetime


class TokenResponse(BaseModel):
    """登录成功响应。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
