from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal

from email_validator import EmailNotValidError, validate_email

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepositoryProtocol
from app.services.auth.exceptions import (
    AccountAlreadyExistsError,
    DisabledAccountError,
    InvalidAccountError,
    InvalidCredentialsError,
    WeakPasswordError,
)

PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{7,14}$")


@dataclass(frozen=True)
class NormalizedAccount:
    """标准化后的登录账号。"""

    type: Literal["email", "phone"]
    value: str


@dataclass(frozen=True)
class AuthResult:
    """登录成功后的内部结果。"""

    user: User
    access_token: str
    expires_in: int


def normalize_account(account: str) -> NormalizedAccount:
    """识别并标准化邮箱或手机号。"""
    normalized = account.strip()

    if "@" in normalized:
        try:
            email = validate_email(
                normalized,
                check_deliverability=False,
            ).normalized.lower()
        except EmailNotValidError as exc:
            raise InvalidAccountError("邮箱格式不正确") from exc
        return NormalizedAccount(type="email", value=email)

    phone = re.sub(r"[\s\-()]", "", normalized)
    if not PHONE_PATTERN.fullmatch(phone):
        raise InvalidAccountError("手机号格式不正确")

    return NormalizedAccount(type="phone", value=phone)


def validate_password_strength(password: str) -> None:
    """执行注册密码强度校验。"""
    if len(password) < 8:
        raise WeakPasswordError("密码至少需要 8 个字符")
    if len(password) > 128:
        raise WeakPasswordError("密码不能超过 128 个字符")
    if not any(char.islower() for char in password):
        raise WeakPasswordError("密码必须包含小写字母")
    if not any(char.isupper() for char in password):
        raise WeakPasswordError("密码必须包含大写字母")
    if not any(char.isdigit() for char in password):
        raise WeakPasswordError("密码必须包含数字")
    if not any(not char.isalnum() for char in password):
        raise WeakPasswordError("密码必须包含特殊字符")


class AuthService:
    """用户注册、登录和访问令牌签发服务。"""

    def __init__(
        self,
        repository: UserRepositoryProtocol,
        *,
        password_hasher: Callable[[str], str] = hash_password,
        password_verifier: Callable[[str, str], bool] = verify_password,
        token_factory: Callable[..., str] = create_access_token,
    ) -> None:
        self._repository = repository
        self._password_hasher = password_hasher
        self._password_verifier = password_verifier
        self._token_factory = token_factory

    def _find_user(self, account: NormalizedAccount) -> User | None:
        if account.type == "email":
            return self._repository.get_by_email(account.value)
        return self._repository.get_by_phone(account.value)

    def register(
        self,
        *,
        account: str,
        password: str,
        display_name: str | None = None,
    ) -> User:
        """注册普通用户，但不负责提交数据库事务。"""
        normalized = normalize_account(account)
        validate_password_strength(password)

        if self._find_user(normalized) is not None:
            raise AccountAlreadyExistsError("该邮箱或手机号已注册")

        email: str | None = None
        phone: str | None = None
        if normalized.type == "email":
            email = normalized.value
        else:
            phone = normalized.value

        user = User(
            email=email,
            phone=phone,
            password_hash=self._password_hasher(password),
            display_name=display_name.strip() if display_name else None,
            role="user",
            status="active",
        )
        return self._repository.add(user)

    def authenticate(
        self,
        *,
        account: str,
        password: str,
    ) -> User:
        """校验账号密码并返回用户。"""
        normalized = normalize_account(account)
        user = self._find_user(normalized)

        if user is None:
            raise InvalidCredentialsError("账号或密码错误")
        if user.status != "active":
            raise DisabledAccountError("账号已被禁用")
        if not self._password_verifier(password, user.password_hash):
            raise InvalidCredentialsError("账号或密码错误")

        user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return user

    def login(
        self,
        *,
        account: str,
        password: str,
    ) -> AuthResult:
        """认证用户并签发 JWT 访问令牌。"""
        user = self.authenticate(account=account, password=password)
        settings = get_settings()
        token = self._token_factory(
            user.id,
            additional_claims={
                "role": user.role,
                "display_name": user.display_name,
            },
        )
        return AuthResult(
            user=user,
            access_token=token,
            expires_in=settings.access_token_expire_minutes * 60,
        )
