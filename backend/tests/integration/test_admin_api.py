from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_admin_service, get_current_admin, get_current_user
from app.main import app
from app.repositories.admin_repository import (
    AdminFeedbackRecord,
    AdminSessionDetailRecord,
    AdminSessionRecord,
)

NOW = datetime(2026, 8, 7, 20, 0, 0)


class FakeAdminService:
    repository: "FakeAdminService"

    def __init__(self) -> None:
        self.repository = self

    def get_overview(self):
        return {
            "total_users": 2,
            "active_users": 2,
            "total_sessions": 3,
            "active_sessions": 2,
            "total_messages": 8,
            "today_questions": 4,
            "total_knowledge_bases": 2,
            "total_documents": 2,
            "feedback_total": 2,
            "positive_feedback": 1,
            "negative_feedback": 1,
            "satisfaction_rate": 50.0,
            "prompt_token_estimate": 120,
            "completion_token_count": 80,
        }

    def list_sessions(self, **kwargs):
        assert kwargs["limit"] == 20
        return [
            AdminSessionRecord(
                id=5,
                user_id=9,
                user_label="测试用户",
                title="退款咨询",
                status="active",
                selected_knowledge_base_id=None,
                message_count=2,
                last_message_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        ], 1

    def get_session_detail(self, session_id):
        assert session_id == 5
        session, _ = self.list_sessions(
            limit=20,
            offset=0,
            status=None,
            query=None,
        )
        return AdminSessionDetailRecord(
            session=session[0],
            messages=(),
        )

    def get_feedback_summary(self):
        return {
            "total": 2,
            "positive": 1,
            "negative": 1,
            "satisfaction_rate": 50.0,
            "by_intent": [],
        }

    def list_feedback(self, *, limit, offset):
        del limit, offset
        return [
            AdminFeedbackRecord(
                id=2,
                message_id=8,
                session_id=5,
                session_title="退款咨询",
                user_id=9,
                user_label="测试用户",
                rating=1,
                comment="有帮助",
                intent="refund",
                assistant_content="退款通常三个工作日内返回",
                created_at=NOW,
            )
        ], 1

    def get_daily_question_trend(self, *, days):
        assert days == 14
        return {
            "days": 14,
            "total_questions": 4,
            "average_per_day": 0.29,
            "items": [
                {
                    "date": date(2026, 8, 7),
                    "question_count": 4,
                }
            ],
        }


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def admin_client():
    service = FakeAdminService()
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        status="active",
    )
    app.dependency_overrides[get_admin_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_admin_openapi_paths_are_registered(admin_client):
    paths = (await admin_client.get("/openapi.json")).json()["paths"]
    assert "/api/v1/admin/overview" in paths
    assert "/api/v1/admin/sessions" in paths
    assert "/api/v1/admin/sessions/{session_id}" in paths
    assert "/api/v1/admin/feedback/summary" in paths
    assert "/api/v1/admin/analytics/daily-questions" in paths


@pytest.mark.anyio
async def test_admin_dashboard_endpoints(admin_client):
    overview = await admin_client.get("/api/v1/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["today_questions"] == 4

    sessions = await admin_client.get("/api/v1/admin/sessions")
    assert sessions.status_code == 200
    assert sessions.json()["items"][0]["title"] == "退款咨询"

    detail = await admin_client.get("/api/v1/admin/sessions/5")
    assert detail.status_code == 200
    assert detail.json()["session"]["id"] == 5

    summary = await admin_client.get("/api/v1/admin/feedback/summary")
    assert summary.status_code == 200
    assert summary.json()["satisfaction_rate"] == 50.0

    feedback = await admin_client.get("/api/v1/admin/feedback")
    assert feedback.status_code == 200
    assert feedback.json()["items"][0]["rating"] == 1

    trend = await admin_client.get(
        "/api/v1/admin/analytics/daily-questions?days=14"
    )
    assert trend.status_code == 200
    assert trend.json()["total_questions"] == 4


@pytest.mark.anyio
async def test_non_admin_is_rejected():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        role="user",
        status="active",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/admin/overview")
    app.dependency_overrides.clear()
    assert response.status_code == 403
