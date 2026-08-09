from __future__ import annotations

from datetime import datetime

import pytest

from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatSessionRecord,
    MessageFeedbackRecord,
)
from app.services.chat.session_service import (
    ChatMessageNotFoundError,
    ChatSessionService,
    ChatValidationError,
)


NOW = datetime(2026, 8, 7, 17, 30, 0)


def session(user_id: int = 7) -> ChatSessionRecord:
    return ChatSessionRecord(
        id=1,
        user_id=user_id,
        title="退款咨询",
        status="active",
        selected_knowledge_base_id=None,
        last_message_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def message(role: str = "assistant") -> ChatMessageRecord:
    return ChatMessageRecord(
        id=2,
        session_id=1,
        user_id=7 if role == "user" else None,
        reply_to_message_id=None,
        role=role,
        content="三个工作日内原路退回。",
        intent="refund",
        routed_knowledge_base_id=None,
        retrieval_status="matched",
        is_fallback=False,
        question_char_count=None,
        prompt_token_estimate=None,
        completion_token_count=None,
        follow_up_suggestions=None,
        stream_completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class Repo:
    def __init__(self) -> None:
        self.owner_id = 7
        self.item = message()
        self.feedback: MessageFeedbackRecord | None = None
        self.commits = 0
        self.rollbacks = 0

    def get_owned_session(
        self,
        *,
        session_id,
        user_id,
        include_archived=True,
    ):
        del include_archived
        if session_id == 1 and user_id == self.owner_id:
            return session(self.owner_id)
        return None

    def get_message(self, message_id):
        return self.item if message_id == self.item.id else None

    def upsert_message_feedback(
        self,
        *,
        message_id,
        user_id,
        rating,
        comment,
    ):
        self.feedback = MessageFeedbackRecord(
            id=10,
            message_id=message_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.feedback

    def list_session_feedback_owned(
        self,
        *,
        session_id,
        user_id,
    ):
        del session_id, user_id
        return [self.feedback] if self.feedback else []

    def delete_message_feedback(
        self,
        *,
        message_id,
        user_id,
    ):
        del message_id, user_id
        existed = self.feedback is not None
        self.feedback = None
        return existed

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def make_service() -> tuple[ChatSessionService, Repo]:
    repo = Repo()
    return ChatSessionService(repo), repo  # type: ignore[arg-type]


def test_like_feedback_is_saved():
    service, repo = make_service()
    result = service.submit_message_feedback(
        message_id=2,
        user_id=7,
        rating=1,
        comment="回答很清楚",
    )

    assert result.rating == 1
    assert result.comment == "回答很清楚"
    assert repo.commits == 1


def test_dislike_feedback_can_update_existing_feedback():
    service, _ = make_service()
    first = service.submit_message_feedback(
        message_id=2,
        user_id=7,
        rating=1,
    )
    second = service.submit_message_feedback(
        message_id=2,
        user_id=7,
        rating=-1,
        comment="没有回答到重点",
    )

    assert first.rating == 1
    assert second.rating == -1
    assert second.comment == "没有回答到重点"


@pytest.mark.parametrize("rating", [0, 2, -2])
def test_invalid_rating_is_rejected(rating):
    service, _ = make_service()
    with pytest.raises(ChatValidationError, match="rating"):
        service.submit_message_feedback(
            message_id=2,
            user_id=7,
            rating=rating,
        )


def test_feedback_comment_is_trimmed_and_empty_becomes_none():
    service, _ = make_service()
    result = service.submit_message_feedback(
        message_id=2,
        user_id=7,
        rating=1,
        comment="   ",
    )
    assert result.comment is None


def test_feedback_on_user_message_is_rejected():
    service, repo = make_service()
    repo.item = message(role="user")

    with pytest.raises(
        ChatValidationError,
        match="assistant",
    ):
        service.submit_message_feedback(
            message_id=2,
            user_id=7,
            rating=1,
        )


def test_other_users_message_is_hidden_as_not_found():
    service, _ = make_service()

    with pytest.raises(ChatMessageNotFoundError):
        service.submit_message_feedback(
            message_id=2,
            user_id=999,
            rating=1,
        )


def test_delete_feedback_is_idempotent_at_service_boundary():
    service, _ = make_service()
    service.submit_message_feedback(
        message_id=2,
        user_id=7,
        rating=1,
    )

    assert service.delete_message_feedback(
        message_id=2,
        user_id=7,
    ) is True
    assert service.delete_message_feedback(
        message_id=2,
        user_id=7,
    ) is False
