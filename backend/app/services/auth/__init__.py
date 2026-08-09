"""认证业务服务。"""

from app.services.auth.exceptions import (
    AccountAlreadyExistsError,
    AuthServiceError,
    DisabledAccountError,
    InvalidAccountError,
    InvalidCredentialsError,
    WeakPasswordError,
)
from app.services.auth.service import (
    AuthResult,
    AuthService,
    NormalizedAccount,
    normalize_account,
    validate_password_strength,
)

__all__ = [
    "AuthService",
    "AuthResult",
    "NormalizedAccount",
    "normalize_account",
    "validate_password_strength",
    "AuthServiceError",
    "InvalidAccountError",
    "WeakPasswordError",
    "AccountAlreadyExistsError",
    "InvalidCredentialsError",
    "DisabledAccountError",
]
