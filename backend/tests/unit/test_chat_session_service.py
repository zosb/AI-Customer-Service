from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatSessionRecord,
    MessageSourceRecord,
)
from app.services.chat.session_service import (
    ChatSessionNotFoundError,
    ChatSessionService,
    ChatValidationError,
    MessageSourceInput,
)


NOW = datetime(2026, 8, 7, 7, 0, 0)


def make_session(
    *,
    session_id: int = 1,
    user_id: int = 7,
    title: str = "新会话",
    status: str = "active",
) -> ChatSessionRecord:
    return ChatSessionRecord(
        id=session_id,
        user_id=user_id,
        title=title,
        status=status,
        selected_knowledge_base_id=None,
        last_message_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_message(
    *,
    message_id: int,
    session_id: int = 1,
    user_id: int | None = 7,
    role: str,
    content: str,
    reply_to_message_id: int | None = None,
) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=message_id,
        session_id=session_id,
        user_id=user_id,
        reply_to_message_id=reply_to_message_id,
        role=role,
        content=content,
        intent=None,
        routed_knowledge_base_id=None,
        retrieval_status=None,
        is_fallback=False,
        question_char_count=(
            len(content)
            if role == "user"
            else None
        ),
        prompt_token_estimate=None,
        completion_token_count=None,
        follow_up_suggestions=None,
        stream_completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.sessions = {
            1: make_session(),
        }
        self.messages: dict[int, ChatMessageRecord] = {}
        self.sources: list[MessageSourceRecord] = []
        self.commits = 0
        self.rollbacks = 0
        self.next_message_id = 1

    def create_session(
        self,
        *,
        user_id,
        title,
        selected_knowledge_base_id=None,
    ):
        session = make_session(
            session_id=max(self.sessions) + 1,
            user_id=user_id,
            title=title,
        )
        session = replace(
            session,
            selected_knowledge_base_id=(
                selected_knowledge_base_id
            ),
        )
        self.sessions[session.id] = session
        return session

    def get_owned_session(
        self,
        *,
        session_id,
        user_id,
        include_archived=True,
    ):
        session = self.sessions.get(session_id)
        if session is None or session.user_id != user_id:
            return None
        if (
            not include_archived
            and session.status != "active"
        ):
            return None
        return session

    def list_sessions(
        self,
        *,
        user_id,
        status=None,
        limit=50,
        offset=0,
    ):
        items = [
            session
            for session in self.sessions.values()
            if session.user_id == user_id
            and (
                status is None
                or session.status == status
            )
        ]
        return items[offset : offset + limit]

    def update_session_title(
        self,
        *,
        session_id,
        user_id,
        title,
    ):
        session = self.get_owned_session(
            session_id=session_id,
            user_id=user_id,
        )
        if session is None:
            raise LookupError("not found")
        updated = replace(session, title=title)
        self.sessions[session_id] = updated
        return updated

    def update_selected_knowledge_base(
        self,
        *,
        session_id,
        user_id,
        knowledge_base_id,
    ):
        session = self.get_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )
        if session is None:
            raise LookupError("not found")
        updated = replace(
            session,
            selected_knowledge_base_id=knowledge_base_id,
        )
        self.sessions[session_id] = updated
        return updated

    def archive_session(
        self,
        *,
        session_id,
        user_id,
    ):
        session = self.get_owned_session(
            session_id=session_id,
            user_id=user_id,
        )
        if session is None:
            raise LookupError("not found")
        updated = replace(
            session,
            status="archived",
        )
        self.sessions[session_id] = updated
        return updated

    def add_message(self, **kwargs):
        message_id = self.next_message_id
        self.next_message_id += 1
        message = make_message(
            message_id=message_id,
            session_id=kwargs["session_id"],
            user_id=kwargs["user_id"],
            role=kwargs["role"],
            content=kwargs["content"],
            reply_to_message_id=kwargs.get(
                "reply_to_message_id"
            ),
        )
        message = replace(
            message,
            intent=kwargs.get("intent"),
            routed_knowledge_base_id=kwargs.get(
                "routed_knowledge_base_id"
            ),
            retrieval_status=kwargs.get(
                "retrieval_status"
            ),
            is_fallback=kwargs.get(
                "is_fallback",
                False,
            ),
            question_char_count=kwargs.get(
                "question_char_count"
            ),
            prompt_token_estimate=kwargs.get(
                "prompt_token_estimate"
            ),
            completion_token_count=kwargs.get(
                "completion_token_count"
            ),
            follow_up_suggestions=(
                list(kwargs["follow_up_suggestions"])
                if kwargs.get(
                    "follow_up_suggestions"
                )
                is not None
                else None
            ),
            stream_completed_at=kwargs.get(
                "stream_completed_at"
            ),
        )
        self.messages[message_id] = message
        return message

    def get_message(self, message_id):
        return self.messages.get(message_id)

    def list_messages_owned(
        self,
        *,
        session_id,
        user_id,
    ):
        if (
            self.get_owned_session(
                session_id=session_id,
                user_id=user_id,
            )
            is None
        ):
            raise LookupError("not found")
        return [
            item
            for item in self.messages.values()
            if item.session_id == session_id
        ]

    def list_recent_messages_owned(
        self,
        *,
        session_id,
        user_id,
        max_messages,
    ):
        if (
            self.get_owned_session(
                session_id=session_id,
                user_id=user_id,
                include_archived=False,
            )
            is None
        ):
            raise LookupError("not found")
        items = [
            item
            for item in self.messages.values()
            if item.session_id == session_id
            and item.role in {"user", "assistant"}
        ]
        return items[-max_messages:]

    def add_message_source(self, **kwargs):
        source = MessageSourceRecord(
            id=len(self.sources) + 1,
            message_id=kwargs["message_id"],
            document_id=kwargs.get("document_id"),
            chunk_id=kwargs.get("chunk_id"),
            document_name=kwargs["document_name"],
            chunk_summary=kwargs["chunk_summary"],
            distance=kwargs.get("distance"),
            similarity_score=kwargs.get(
                "similarity_score"
            ),
            rank=kwargs["rank"],
            created_at=NOW,
        )
        self.sources.append(source)
        return source

    def list_message_sources_owned(
        self,
        *,
        message_id,
        user_id,
    ):
        del user_id
        return [
            source
            for source in self.sources
            if source.message_id == message_id
        ]

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def service():
    repository = FakeRepository()
    chat_service = ChatSessionService(
        repository,  # type: ignore[arg-type]
    )
    chat_service.question_max_length = 500
    chat_service.context_history_rounds = 6
    return chat_service, repository


def test_create_session_normalizes_title(service):
    chat_service, repository = service

    session = chat_service.create_session(
        user_id=7,
        title="  售后   咨询  ",
    )

    assert session.title == "售后 咨询"
    assert repository.commits == 1


def test_empty_or_overlong_title_is_rejected(service):
    chat_service, _ = service

    with pytest.raises(
        ChatValidationError,
        match="标题不能为空",
    ):
        chat_service.create_session(
            user_id=7,
            title="   ",
        )

    with pytest.raises(
        ChatValidationError,
        match="255",
    ):
        chat_service.create_session(
            user_id=7,
            title="x" * 256,
        )


def test_ownership_isolation_hides_other_users_session(
    service,
):
    chat_service, _ = service

    with pytest.raises(
        ChatSessionNotFoundError,
        match="无权访问",
    ):
        chat_service.get_session(
            session_id=1,
            user_id=999,
        )


def test_first_user_message_auto_titles_session(service):
    chat_service, repository = service

    message = chat_service.add_user_message(
        session_id=1,
        user_id=7,
        content="退款审核通过以后多久能到账？",
        intent="refund",
    )

    assert message.role == "user"
    assert message.question_char_count == len(
        "退款审核通过以后多久能到账？"
    )
    assert repository.sessions[1].title == (
        "退款审核通过以后多久能到账？"
    )


def test_user_question_length_limit_is_enforced(service):
    chat_service, _ = service
    chat_service.question_max_length = 5

    with pytest.raises(
        ChatValidationError,
        match="不能超过 5 字",
    ):
        chat_service.add_user_message(
            session_id=1,
            user_id=7,
            content="123456",
        )


def test_assistant_message_preserves_rag_metadata(service):
    chat_service, repository = service

    user_message = chat_service.add_user_message(
        session_id=1,
        user_id=7,
        content="退款多久到？",
    )
    assistant = chat_service.add_assistant_message(
        session_id=1,
        user_id=7,
        content="审核通过后通常三个工作日内到账。",
        reply_to_message_id=user_message.id,
        intent="refund",
        routed_knowledge_base_id=None,
        retrieval_status="matched",
        is_fallback=False,
        prompt_token_estimate=120,
        completion_token_count=18,
        follow_up_suggestions=[
            "如何查询退款状态？",
            "超过三天没到账怎么办？",
        ],
    )

    assert assistant.role == "assistant"
    assert assistant.user_id is None
    assert assistant.reply_to_message_id == (
        user_message.id
    )
    assert assistant.retrieval_status == "matched"
    assert assistant.prompt_token_estimate == 120
    assert assistant.completion_token_count == 18
    assert assistant.follow_up_suggestions == [
        "如何查询退款状态？",
        "超过三天没到账怎么办？",
    ]
    assert assistant.stream_completed_at is not None
    assert repository.commits == 2


def test_assistant_reply_must_target_user_message(
    service,
):
    chat_service, _ = service

    assistant = chat_service.add_assistant_message(
        session_id=1,
        user_id=7,
        content="第一条 AI 消息",
    )

    with pytest.raises(
        ChatValidationError,
        match="必须指向当前会话的用户消息",
    ):
        chat_service.add_assistant_message(
            session_id=1,
            user_id=7,
            content="错误回复",
            reply_to_message_id=assistant.id,
        )


def test_recent_context_keeps_last_n_rounds(service):
    chat_service, _ = service

    for index in range(1, 4):
        user_message = (
            chat_service.add_user_message(
                session_id=1,
                user_id=7,
                content=f"问题{index}",
            )
        )
        chat_service.add_assistant_message(
            session_id=1,
            user_id=7,
            content=f"回答{index}",
            reply_to_message_id=user_message.id,
        )

    context = chat_service.recent_context(
        session_id=1,
        user_id=7,
        rounds=2,
    )

    assert [
        (item.role, item.content)
        for item in context
    ] == [
        ("user", "问题2"),
        ("assistant", "回答2"),
        ("user", "问题3"),
        ("assistant", "回答3"),
    ]


def test_archived_session_rejects_new_message(service):
    chat_service, _ = service

    archived = chat_service.archive_session(
        session_id=1,
        user_id=7,
    )
    assert archived.status == "archived"

    with pytest.raises(
        ChatSessionNotFoundError,
    ):
        chat_service.add_user_message(
            session_id=1,
            user_id=7,
            content="不能再写入",
        )


def test_message_sources_require_unique_positive_rank(
    service,
):
    chat_service, repository = service

    user_message = chat_service.add_user_message(
        session_id=1,
        user_id=7,
        content="退款规则是什么？",
    )
    assistant = chat_service.add_assistant_message(
        session_id=1,
        user_id=7,
        content="根据退款政策……",
        reply_to_message_id=user_message.id,
        retrieval_status="matched",
    )

    with pytest.raises(
        ChatValidationError,
        match="不能重复",
    ):
        chat_service.add_message_sources(
            message_id=assistant.id,
            user_id=7,
            sources=[
                MessageSourceInput(
                    document_name="退款政策.txt",
                    chunk_summary="片段 A",
                    rank=1,
                ),
                MessageSourceInput(
                    document_name="FAQ.md",
                    chunk_summary="片段 B",
                    rank=1,
                ),
            ],
        )

    created = chat_service.add_message_sources(
        message_id=assistant.id,
        user_id=7,
        sources=[
            MessageSourceInput(
                document_name="退款政策.txt",
                chunk_summary="退款审核通过后三个工作日退款。",
                rank=1,
                distance=0.18,
                similarity_score=0.82,
            ),
            MessageSourceInput(
                document_name="FAQ.md",
                chunk_summary="超过预计时间请联系客服。",
                rank=2,
                distance=0.30,
                similarity_score=0.70,
            ),
        ],
    )

    assert [item.rank for item in created] == [1, 2]
    assert len(repository.sources) == 2
