from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepositoryProtocol(Protocol):
    """认证服务依赖的用户仓储接口。"""

    def get_by_id(self, user_id: int) -> User | None:
        ...

    def get_by_email(self, email: str) -> User | None:
        ...

    def get_by_phone(self, phone: str) -> User | None:
        ...

    def add(self, user: User) -> User:
        ...


class SqlAlchemyUserRepository:
    """基于 SQLAlchemy Session 的用户仓储。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self._session.scalar(statement)

    def get_by_phone(self, phone: str) -> User | None:
        statement = select(User).where(User.phone == phone)
        return self._session.scalar(statement)

    def add(self, user: User) -> User:
        self._session.add(user)
        self._session.flush()
        self._session.refresh(user)
        return user
