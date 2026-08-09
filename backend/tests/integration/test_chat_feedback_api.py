from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_chat_session_service,
    get_current_user,
)
from app.main import app
from app.repositories.chat_repository import MessageFeedbackRecord
from app.services.chat.session_service import ChatValidationError


NOW = datetime(2026, 8, 7, 17, 30, 0)


class FakeFeedbackService:
    def __init__(self) -> None:
        self.feedback: MessageFeedbackRecord | None = None

    def list_session_feedback(self, *, session_id, user_id):
        assert session_id == 1
        assert user_id == 99
        return [self.feedback] if self.feedback else []

    def submit_message_feedback(
        self,
        *,
        message_id,
        user_id,
        rating,
        comment,
    ):
        if message_id == 1:
            raise ChatValidationError(
                "只能对 AI assistant 回答提交反馈"
            )
        self.feedback = MessageFeedbackRecord(
            id=5,
            message_id=message_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.feedback

    def delete_message_feedback(
        self,
        *,
        message_id,
        user_id,
    ):
        del user_id
        if self.feedback and self.feedback.message_id == message_id:
            self.feedback = None
            return True
        return False


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    service = FakeFeedbackService()
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
        yield test_client

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_feedback_openapi_paths_are_registered(client):
    response = await client.get("/openapi.json")
    paths = response.json()["paths"]

    assert (
        "/api/v1/chat/messages/{message_id}/feedback"
        in paths
    )
    assert "put" in paths[
        "/api/v1/chat/messages/{message_id}/feedback"
    ]
    assert "delete" in paths[
        "/api/v1/chat/messages/{message_id}/feedback"
    ]
    assert (
        "/api/v1/chat/sessions/{session_id}/feedback"
        in paths
    )


@pytest.mark.anyio
async def test_submit_update_list_and_delete_feedback(client):
    liked = await client.put(
        "/api/v1/chat/messages/2/feedback",
        json={
            "rating": 1,
            "comment": "回答很清楚",
        },
    )
    assert liked.status_code == 200
    assert liked.json()["rating"] == 1

    disliked = await client.put(
        "/api/v1/chat/messages/2/feedback",
        json={
            "rating": -1,
            "comment": "希望更具体",
        },
    )
    assert disliked.status_code == 200
    assert disliked.json()["rating"] == -1
    assert disliked.json()["comment"] == "希望更具体"

    listing = await client.get(
        "/api/v1/chat/sessions/1/feedback"
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["message_id"] == 2

    deleted = await client.delete(
        "/api/v1/chat/messages/2/feedback"
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    listing_after = await client.get(
        "/api/v1/chat/sessions/1/feedback"
    )
    assert listing_after.json() == []


@pytest.mark.anyio
async def test_user_message_feedback_is_rejected(client):
    response = await client.put(
        "/api/v1/chat/messages/1/feedback",
        json={"rating": 1},
    )
    assert response.status_code == 422
