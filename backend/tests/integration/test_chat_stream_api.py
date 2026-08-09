from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_chat_streaming_answer_service,
    get_current_user,
)
from app.main import app
from app.services.chat.streaming_answer_service import (
    ChatStreamPlan,
)


class FakeStreamingService:
    def prepare(
        self,
        *,
        session_id,
        user_id,
        question,
    ):
        assert session_id == 5
        assert user_id == 99
        assert question == "退款多久？"
        return SimpleNamespace(
            session_id=session_id,
        )

    def iter_sse(self, plan):
        assert plan.session_id == 5
        yield (
            'event: meta\n'
            'data: {"session_id":5}\n\n'
        )
        yield (
            'event: delta\n'
            'data: {"content":"三个工作日"}\n\n'
        )
        yield (
            'event: done\n'
            'data: {"assistant_message_id":8,'
            '"content":"三个工作日","is_fallback":false}\n\n'
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=99, status="active")
    )
    app.dependency_overrides[
        get_chat_streaming_answer_service
    ] = lambda: FakeStreamingService()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_stream_chat_path_is_registered(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert (
        "/api/v1/chat/sessions/{session_id}/messages"
        in response.json()["paths"]
    )
    assert (
        "post"
        in response.json()["paths"][
            "/api/v1/chat/sessions/{session_id}/messages"
        ]
    )


@pytest.mark.anyio
async def test_stream_chat_returns_sse(client):
    response = await client.post(
        "/api/v1/chat/sessions/5/messages",
        json={"question": "退款多久？"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "text/event-stream"
    )
    text = response.text
    assert "event: meta" in text
    assert "event: delta" in text
    assert "event: done" in text
    assert "三个工作日" in text
