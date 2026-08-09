from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.models.user import User
from app.services.auth import (
    AccountAlreadyExistsError,
    AuthService,
    DisabledAccountError,
    InvalidAccountError,
    InvalidCredentialsError,
    WeakPasswordError,
    normalize_account,
    validate_password_strength,
)


@dataclass
class FakeUserRepository:
    users: list[User] = field(default_factory=list)
    next_id: int = 1

    def get_by_email(self, email: str) -> User | None:
        return next(
            (user for user in self.users if user.email == email),
            None,
        )

    def get_by_phone(self, phone: str) -> User | None:
        return next(
            (user for user in self.users if user.phone == phone),
            None,
        )

    def add(self, user: User) -> User:
        user.id = self.next_id
        self.next_id += 1
        self.users.append(user)
        return user


def fake_hash(password: str) -> str:
    return f"hashed::{password}"


def fake_verify(password: str, password_hash: str) -> bool:
    return password_hash == f"hashed::{password}"


def fake_token_factory(
    subject: str | int,
    *,
    additional_claims: dict[str, object] | None = None,
) -> str:
    role = additional_claims["role"] if additional_claims else "none"
    return f"token::{subject}::{role}"


@pytest.fixture
def repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def service(repository: FakeUserRepository) -> AuthService:
    return AuthService(
        repository,
        password_hasher=fake_hash,
        password_verifier=fake_verify,
        token_factory=fake_token_factory,
    )


def test_normalize_email_account() -> None:
    account = normalize_account("  Tester@Example.COM ")

    assert account.type == "email"
    assert account.value == "tester@example.com"


def test_normalize_phone_account() -> None:
    account = normalize_account("+86 138-0013-8000")

    assert account.type == "phone"
    assert account.value == "+8613800138000"


@pytest.mark.parametrize(
    "account",
    ["not-an-email@", "abc", "12345", "++8613800138000"],
)
def test_invalid_account_is_rejected(account: str) -> None:
    with pytest.raises(InvalidAccountError):
        normalize_account(account)


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("Aa1!", "至少需要 8"),
        ("PASSWORD1!", "小写字母"),
        ("password1!", "大写字母"),
        ("Password!", "数字"),
        ("Password1", "特殊字符"),
    ],
)
def test_weak_password_is_rejected(
    password: str,
    message: str,
) -> None:
    with pytest.raises(WeakPasswordError, match=message):
        validate_password_strength(password)


def test_register_email_user(
    service: AuthService,
    repository: FakeUserRepository,
) -> None:
    user = service.register(
        account="NewUser@Example.com",
        password="StrongPass1!",
        display_name=" 新用户 ",
    )

    assert user.id == 1
    assert user.email == "newuser@example.com"
    assert user.phone is None
    assert user.display_name == "新用户"
    assert user.password_hash == "hashed::StrongPass1!"
    assert repository.users == [user]


def test_register_phone_user(
    service: AuthService,
) -> None:
    user = service.register(
        account="138 0013 8000",
        password="StrongPass1!",
    )

    assert user.phone == "13800138000"
    assert user.email is None


def test_duplicate_account_is_rejected(
    service: AuthService,
) -> None:
    service.register(
        account="duplicate@example.com",
        password="StrongPass1!",
    )

    with pytest.raises(
        AccountAlreadyExistsError,
        match="已注册",
    ):
        service.register(
            account="DUPLICATE@example.com",
            password="StrongPass1!",
        )


def test_login_returns_access_token(
    service: AuthService,
) -> None:
    user = service.register(
        account="login@example.com",
        password="StrongPass1!",
        display_name="登录用户",
    )

    result = service.login(
        account="LOGIN@example.com",
        password="StrongPass1!",
    )

    assert result.user is user
    assert result.access_token == f"token::{user.id}::user"
    assert result.expires_in > 0
    assert user.last_login_at is not None


def test_wrong_password_is_rejected(
    service: AuthService,
) -> None:
    service.register(
        account="wrong@example.com",
        password="StrongPass1!",
    )

    with pytest.raises(
        InvalidCredentialsError,
        match="账号或密码错误",
    ):
        service.login(
            account="wrong@example.com",
            password="WrongPass1!",
        )


def test_missing_account_uses_same_generic_error(
    service: AuthService,
) -> None:
    with pytest.raises(
        InvalidCredentialsError,
        match="账号或密码错误",
    ):
        service.login(
            account="missing@example.com",
            password="StrongPass1!",
        )


def test_disabled_account_is_rejected(
    service: AuthService,
) -> None:
    user = service.register(
        account="disabled@example.com",
        password="StrongPass1!",
    )
    user.status = "disabled"

    with pytest.raises(
        DisabledAccountError,
        match="账号已被禁用",
    ):
        service.login(
            account="disabled@example.com",
            password="StrongPass1!",
        )
