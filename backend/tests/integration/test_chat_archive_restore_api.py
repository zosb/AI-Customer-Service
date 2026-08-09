from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_chat_session_service,
    get_current_user,
)
from app.main import app
from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatSessionRecord,
)
from app.services.chat.session_service import ChatSessionNotFoundError


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


def make_message(
    *,
    message_id: int,
    role: str,
    content: str,
) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=message_id,
        session_id=21,
        user_id=7 if role == "user" else None,
        reply_to_message_id=None,
        role=role,
        content=content,
        intent="refund",
        routed_knowledge_base_id=None,
        retrieval_status="matched" if role == "assistant" else None,
        is_fallback=False,
        question_char_count=len(content) if role == "user" else None,
        prompt_token_estimate=None,
        completion_token_count=None,
        follow_up_suggestions=None,
        stream_completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeChatService:
    def __init__(self) -> None:
        self.session = make_session()
        self.messages = [
            make_message(
                message_id=31,
                role="user",
                content="退款审核通过后多久能到账？",
            ),
            make_message(
                message_id=32,
                role="assistant",
                content="通常会在三个工作日内原路退回。",
            ),
        ]

    def list_sessions(
        self,
        *,
        user_id,
        status=None,
        limit=50,
        offset=0,
    ):
        if self.session.user_id != user_id:
            return []
        if status is not None and self.session.status != status:
            return []
        return [self.session][offset : offset + limit]

    def count_sessions(self, *, user_id, status=None):
        return len(
            self.list_sessions(
                user_id=user_id,
                status=status,
                limit=200,
                offset=0,
            )
        )

    def get_session(
        self,
        *,
        session_id,
        user_id,
        include_archived=True,
    ):
        if self.session.id != session_id or self.session.user_id != user_id:
            raise ChatSessionNotFoundError("会话不存在或无权访问")
        if not include_archived and self.session.status != "active":
            raise ChatSessionNotFoundError("会话不存在或无权访问")
        return self.session

    def list_messages(self, *, session_id, user_id):
        self.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=True,
        )
        return self.messages

    def restore_session(self, *, session_id, user_id):
        self.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=True,
        )
        self.session = replace(self.session, status="active")
        return self.session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    service = FakeChatService()

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7,
        status="active",
    )
    app.dependency_overrides[get_chat_session_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client, service

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_restore_path_is_registered(client):
    test_client, _ = client

    response = await test_client.get("/openapi.json")
    assert response.status_code == 200
    assert (
        "/api/v1/chat/sessions/{session_id}/restore"
        in response.json()["paths"]
    )


@pytest.mark.anyio
async def test_archived_sessions_can_be_listed_and_read(client):
    test_client, _ = client

    listing = await test_client.get(
        "/api/v1/chat/sessions",
        params={"status": "archived"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["status"] == "archived"

    history = await test_client.get(
        "/api/v1/chat/sessions/21/messages"
    )
    assert history.status_code == 200
    assert history.json()["session"]["status"] == "archived"
    assert [item["role"] for item in history.json()["messages"]] == [
        "user",
        "assistant",
    ]


@pytest.mark.anyio
async def test_restore_moves_session_back_to_active_list(client):
    test_client, service = client

    restored = await test_client.post(
        "/api/v1/chat/sessions/21/restore"
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert service.session.status == "active"

    active = await test_client.get(
        "/api/v1/chat/sessions",
        params={"status": "active"},
    )
    archived = await test_client.get(
        "/api/v1/chat/sessions",
        params={"status": "archived"},
    )
    assert active.json()["total"] == 1
    assert archived.json()["total"] == 0


@pytest.mark.anyio
async def test_other_users_archived_session_cannot_be_restored(client):
    test_client, service = client
    service.session = replace(service.session, user_id=999)

    response = await test_client.post(
        "/api/v1/chat/sessions/21/restore"
    )
    assert response.status_code == 404
