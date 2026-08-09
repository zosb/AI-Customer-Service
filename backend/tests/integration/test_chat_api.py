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
    MessageSourceRecord,
)
from app.services.chat.session_service import (
    ChatSessionNotFoundError,
)


NOW = datetime(2026, 8, 7, 8, 0, 0)


def make_session(
    *,
    session_id: int = 1,
    user_id: int = 99,
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
    role: str,
    content: str,
) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=message_id,
        session_id=session_id,
        user_id=99 if role == "user" else None,
        reply_to_message_id=None,
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


class FakeChatService:
    def __init__(self) -> None:
        self.session = make_session()
        self.messages = [
            make_message(
                message_id=1,
                role="user",
                content="退款多久到？",
            ),
            make_message(
                message_id=2,
                role="assistant",
                content="通常三个工作日内。",
            ),
        ]
        self.sources = [
            MessageSourceRecord(
                id=1,
                message_id=2,
                document_id=5,
                chunk_id=9,
                document_name="退款政策.txt",
                chunk_summary="审核通过后三个工作日退款。",
                distance=0.18,
                similarity_score=0.82,
                rank=1,
                created_at=NOW,
            )
        ]

    def create_session(
        self,
        *,
        user_id,
        title,
        selected_knowledge_base_id=None,
    ):
        self.session = make_session(
            session_id=2,
            user_id=user_id,
            title=title,
        )
        self.session = replace(
            self.session,
            selected_knowledge_base_id=(
                selected_knowledge_base_id
            ),
        )
        return self.session

    def list_sessions(
        self,
        *,
        user_id,
        status=None,
        limit=50,
        offset=0,
    ):
        del status
        if self.session.user_id != user_id:
            return []
        return [self.session][offset : offset + limit]

    def count_sessions(
        self,
        *,
        user_id,
        status=None,
    ):
        del status
        return 1 if self.session.user_id == user_id else 0

    def get_session(
        self,
        *,
        session_id,
        user_id,
        include_archived=True,
    ):
        del include_archived
        if (
            self.session.id != session_id
            or self.session.user_id != user_id
        ):
            raise ChatSessionNotFoundError(
                "会话不存在或无权访问"
            )
        return self.session

    def rename_session(
        self,
        *,
        session_id,
        user_id,
        title,
    ):
        self.get_session(
            session_id=session_id,
            user_id=user_id,
        )
        self.session = replace(
            self.session,
            title=title.strip(),
        )
        return self.session

    def select_knowledge_base(
        self,
        *,
        session_id,
        user_id,
        knowledge_base_id,
    ):
        self.get_session(
            session_id=session_id,
            user_id=user_id,
        )
        self.session = replace(
            self.session,
            selected_knowledge_base_id=knowledge_base_id,
        )
        return self.session

    def archive_session(
        self,
        *,
        session_id,
        user_id,
    ):
        self.get_session(
            session_id=session_id,
            user_id=user_id,
        )
        self.session = replace(
            self.session,
            status="archived",
        )
        return self.session

    def list_messages(
        self,
        *,
        session_id,
        user_id,
    ):
        self.get_session(
            session_id=session_id,
            user_id=user_id,
        )
        return self.messages

    def list_message_sources(
        self,
        *,
        message_id,
        user_id,
    ):
        del user_id
        return [
            item
            for item in self.sources
            if item.message_id == message_id
        ]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    service = FakeChatService()

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=99, status="active")
    )
    app.dependency_overrides[
        get_chat_session_service
    ] = lambda: service

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client, service

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_chat_openapi_paths_are_registered(client):
    test_client, _ = client

    response = await test_client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert "/api/v1/chat/sessions" in paths
    assert "/api/v1/chat/sessions/{session_id}" in paths
    assert (
        "/api/v1/chat/sessions/{session_id}/messages"
        in paths
    )
    assert (
        "/api/v1/chat/messages/{message_id}/sources"
        in paths
    )


@pytest.mark.anyio
async def test_create_and_list_session(client):
    test_client, _ = client

    created = await test_client.post(
        "/api/v1/chat/sessions",
        json={
            "title": "售后咨询",
        },
    )
    assert created.status_code == 201
    assert created.json()["title"] == "售后咨询"

    listing = await test_client.get(
        "/api/v1/chat/sessions"
    )
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "售后咨询"


@pytest.mark.anyio
async def test_other_users_session_returns_404(client):
    test_client, service = client
    service.session = replace(
        service.session,
        user_id=12345,
    )

    response = await test_client.get(
        f"/api/v1/chat/sessions/{service.session.id}"
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_patch_session_updates_title_and_kb(client):
    test_client, service = client

    response = await test_client.patch(
        "/api/v1/chat/sessions/1",
        json={
            "title": "退款咨询",
            "selected_knowledge_base_id": 7,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "退款咨询"
    assert data["selected_knowledge_base_id"] == 7
    assert service.session.title == "退款咨询"


@pytest.mark.anyio
async def test_get_message_history(client):
    test_client, _ = client

    response = await test_client.get(
        "/api/v1/chat/sessions/1/messages"
    )
    assert response.status_code == 200

    data = response.json()
    assert [item["role"] for item in data["messages"]] == [
        "user",
        "assistant",
    ]
    assert data["messages"][1]["content"] == (
        "通常三个工作日内。"
    )


@pytest.mark.anyio
async def test_get_message_sources(client):
    test_client, _ = client

    response = await test_client.get(
        "/api/v1/chat/messages/2/sources"
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["document_name"] == "退款政策.txt"
    assert data[0]["rank"] == 1


@pytest.mark.anyio
async def test_archive_session(client):
    test_client, service = client

    response = await test_client.delete(
        "/api/v1/chat/sessions/1"
    )
    assert response.status_code == 200
    assert response.json() == {
        "session_id": 1,
        "status": "archived",
    }
    assert service.session.status == "archived"
