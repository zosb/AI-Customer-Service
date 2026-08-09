class AuthServiceError(ValueError):
    """认证业务异常基类。"""


class InvalidAccountError(AuthServiceError):
    """邮箱或手机号格式不正确。"""


class WeakPasswordError(AuthServiceError):
    """密码不满足安全要求。"""


class AccountAlreadyExistsError(AuthServiceError):
    """邮箱或手机号已经注册。"""


class InvalidCredentialsError(AuthServiceError):
    """账号或密码错误。"""


class DisabledAccountError(AuthServiceError):
    """账号已被禁用。"""
