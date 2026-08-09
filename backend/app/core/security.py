from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()
_RESERVED_CLAIMS = {"sub", "iat", "exp", "type"}


class AccessTokenError(ValueError):
    """访问令牌无效、过期或类型不正确。"""


def hash_password(plain_password: str) -> str:
    """使用 Argon2id 为明文密码生成不可逆哈希。"""
    if not plain_password:
        raise ValueError("密码不能为空")
    return _password_hash.hash(plain_password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """验证明文密码是否与已保存的哈希一致。"""
    if not plain_password or not password_hash:
        return False

    try:
        return _password_hash.verify(plain_password, password_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | int,
    *,
    expires_delta: timedelta | None = None,
    additional_claims: Mapping[str, Any] | None = None,
) -> str:
    """创建带过期时间的 HS256 JWT 访问令牌。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }

    if additional_claims:
        conflicting_claims = _RESERVED_CLAIMS.intersection(
            additional_claims.keys()
        )
        if conflicting_claims:
            names = ", ".join(sorted(conflicting_claims))
            raise ValueError(f"附加声明不能覆盖保留字段：{names}")
        payload.update(additional_claims)

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """校验并解码访问令牌。"""
    if not token:
        raise AccessTokenError("访问令牌不能为空")

    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={
                "require": ["sub", "iat", "exp", "type"],
            },
        )
    except InvalidTokenError as exc:
        raise AccessTokenError("访问令牌无效或已过期") from exc

    if payload.get("type") != "access":
        raise AccessTokenError("令牌类型不正确")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise AccessTokenError("访问令牌缺少有效用户标识")

    return payload
