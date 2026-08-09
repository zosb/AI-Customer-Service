from datetime import timedelta

import jwt
import pytest

import app.core.security as security
from app.core.config import Settings
from app.core.security import (
    AccessTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

TEST_SECRET = (
    "UnitTestJwtSecret-0123456789-"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdef"
)


@pytest.fixture(autouse=True)
def use_test_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """所有测试使用独立且长度足够的 JWT 密钥。"""
    settings = Settings(
        _env_file=None,
        jwt_secret_key=TEST_SECRET,
        jwt_algorithm="HS256",
        access_token_expire_minutes=30,
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    return settings


def test_password_hash_uses_argon2id_and_verifies() -> None:
    hashed = hash_password("AuthTest123!")

    assert hashed.startswith("$argon2id$")
    assert verify_password("AuthTest123!", hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_same_password_generates_different_salted_hashes() -> None:
    first = hash_password("SamePassword123!")
    second = hash_password("SamePassword123!")

    assert first != second
    assert verify_password("SamePassword123!", first) is True
    assert verify_password("SamePassword123!", second) is True


def test_empty_password_is_rejected() -> None:
    with pytest.raises(ValueError, match="密码不能为空"):
        hash_password("")

    assert verify_password("", "not-a-hash") is False
    assert verify_password("password", "") is False


def test_access_token_round_trip_preserves_subject_and_claims() -> None:
    token = create_access_token(
        42,
        additional_claims={
            "role": "admin",
            "display_name": "测试管理员",
        },
    )

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["role"] == "admin"
    assert payload["display_name"] == "测试管理员"
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] > payload["iat"]


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(
        "1",
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(
        AccessTokenError,
        match="访问令牌无效或已过期",
    ):
        decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected() -> None:
    foreign_token = jwt.encode(
        {
            "sub": "1",
            "iat": 1,
            "exp": 4102444800,
            "type": "access",
        },
        "AnotherJwtSecret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        algorithm="HS256",
    )

    with pytest.raises(
        AccessTokenError,
        match="访问令牌无效或已过期",
    ):
        decode_access_token(foreign_token)


def test_wrong_token_type_is_rejected() -> None:
    settings = security.get_settings()
    refresh_token = jwt.encode(
        {
            "sub": "1",
            "iat": 1,
            "exp": 4102444800,
            "type": "refresh",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(
        AccessTokenError,
        match="令牌类型不正确",
    ):
        decode_access_token(refresh_token)


def test_additional_claims_cannot_override_reserved_claims() -> None:
    with pytest.raises(
        ValueError,
        match="附加声明不能覆盖保留字段",
    ):
        create_access_token(
            "1",
            additional_claims={"sub": "999"},
        )
