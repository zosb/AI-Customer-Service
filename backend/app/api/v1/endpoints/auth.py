from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.deps import CurrentUser, DatabaseSession
from app.repositories.user_repository import SqlAlchemyUserRepository
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)
from app.services.auth import (
    AccountAlreadyExistsError,
    AuthService,
    DisabledAccountError,
    InvalidAccountError,
    InvalidCredentialsError,
    WeakPasswordError,
)

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="使用邮箱或手机号注册",
)
def register(
    payload: RegisterRequest,
    database: DatabaseSession,
) -> UserPublic:
    """注册普通用户并持久化到 MySQL。"""
    service = AuthService(SqlAlchemyUserRepository(database))

    try:
        user = service.register(
            account=payload.account,
            password=payload.password,
            display_name=payload.display_name,
        )
        database.commit()
        database.refresh(user)
        return UserPublic.model_validate(user)
    except InvalidAccountError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except WeakPasswordError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except AccountAlreadyExistsError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱或手机号已注册",
        ) from exc
    except SQLAlchemyError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="使用邮箱或手机号登录",
)
def login(
    payload: LoginRequest,
    database: DatabaseSession,
) -> TokenResponse:
    """验证账号密码、记录登录时间并签发 JWT。"""
    service = AuthService(SqlAlchemyUserRepository(database))

    try:
        result = service.login(
            account=payload.account,
            password=payload.password,
        )
        database.commit()
        database.refresh(result.user)
        return TokenResponse(
            access_token=result.access_token,
            expires_in=result.expires_in,
            user=UserPublic.model_validate(result.user),
        )
    except (InvalidAccountError, InvalidCredentialsError) as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except DisabledAccountError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc


@router.get(
    "/me",
    response_model=UserPublic,
    summary="获取当前登录用户",
)
def get_me(current_user: CurrentUser) -> UserPublic:
    """返回 Bearer JWT 对应的当前用户。"""
    return UserPublic.model_validate(current_user)
