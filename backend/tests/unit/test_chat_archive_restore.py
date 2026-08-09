from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from app.repositories.chat_repository import ChatSessionRecord
from app.services.chat.session_service import (
    ChatSessionNotFoundError,
    ChatSessionService,
)


NOW = datetime(2026, 8, 8, 7, 0, 0)


def make_session(
    *,
    session_id: int = 21,
    user_id: int = 7,
    status: str = "archived",
) -> ChatSessionRecord:
    return ChatSessionRecord(
        id=session_id,
        user_id=user_id,
        title="历史退款咨询",
        status=status,
        selected_knowledge_base_id=None,
        last_message_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.session = make_session()
        self.commits = 0
        self.rollbacks = 0

    def get_owned_session(
        self,
        *,
        session_id: int,
        user_id: int,
        include_archived: bool = True,
    ) -> ChatSessionRecord | None:
        if self.session.id != session_id or self.session.user_id != user_id:
            return None
        if not include_archived and self.session.status != "active":
            return None
        return self.session

    def restore_session(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> ChatSessionRecord:
        session = self.get_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=True,
        )
        if session is None:
            raise LookupError("会话不存在、无权访问或状态不可用")
        self.session = replace(session, status="active")
        return self.session

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_restore_archived_session_changes_status_and_commits() -> None:
    repository = FakeRepository()
    service = ChatSessionService(repository)  # type: ignore[arg-type]

    restored = service.restore_session(
        session_id=21,
        user_id=7,
    )

    assert restored.status == "active"
    assert repository.session.status == "active"
    assert repository.commits == 1
    assert repository.rollbacks == 0


def test_restore_other_users_session_is_rejected() -> None:
    repository = FakeRepository()
    service = ChatSessionService(repository)  # type: ignore[arg-type]

    with pytest.raises(ChatSessionNotFoundError):
        service.restore_session(
            session_id=21,
            user_id=999,
        )

    assert repository.commits == 0


def test_archived_session_cannot_be_renamed_before_restore() -> None:
    repository = FakeRepository()
    service = ChatSessionService(repository)  # type: ignore[arg-type]

    with pytest.raises(ChatSessionNotFoundError):
        service.rename_session(
            session_id=21,
            user_id=7,
            title="不应该直接修改",
        )

    assert repository.session.title == "历史退款咨询"
    assert repository.commits == 0
