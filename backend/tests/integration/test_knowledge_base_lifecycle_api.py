from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_current_user,
    get_knowledge_repository,
    get_knowledge_upload_service,
)
from app.main import app
from app.repositories.knowledge_repository import (
    KnowledgeRepositoryError,
)


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        now = datetime(2026, 8, 8, 14, 45, 0)
        self.base = SimpleNamespace(
            id=7,
            name="退款政策",
            description="退款相关企业政策",
            routing_description="退款、到账、原路退回",
            is_active=True,
            created_by=99,
            deleted_at=None,
            created_at=now,
            updated_at=now,
        )
        self.document_count = 2

    def get_base_for_management(self, knowledge_base_id: int):
        if knowledge_base_id != self.base.id or self.base.deleted_at is not None:
            raise KnowledgeRepositoryError("知识库不存在或已删除")
        return self.base

    def update_knowledge_base(self, knowledge_base, *, values):
        for key, value in values.items():
            setattr(knowledge_base, key, value)
        knowledge_base.updated_at = datetime(2026, 8, 8, 14, 46, 0)
        return knowledge_base

    def count_documents(self, *, knowledge_base_id=None):
        if knowledge_base_id == self.base.id:
            return self.document_count
        return 0

    def rollback(self):
        return None


class FakeKnowledgeUploadService:
    def delete_knowledge_base(self, knowledge_base_id: int):
        if knowledge_base_id != 7:
            raise KnowledgeRepositoryError("知识库不存在或已删除")
        return SimpleNamespace(
            knowledge_base_id=7,
            document_count=2,
            chunk_count=5,
            vector_count=5,
            disk_files_removed=True,
            disk_cleanup_failures=(),
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    repository = FakeKnowledgeRepository()
    service = FakeKnowledgeUploadService()

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=99, status="active")
    )
    app.dependency_overrides[
        get_knowledge_repository
    ] = lambda: repository
    app.dependency_overrides[
        get_knowledge_upload_service
    ] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client, repository

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_knowledge_base_lifecycle_paths_are_registered(client):
    test_client, _ = client

    response = await test_client.get("/openapi.json")
    assert response.status_code == 200

    operations = response.json()["paths"][
        "/api/v1/knowledge/bases/{knowledge_base_id}"
    ]
    assert "patch" in operations
    assert "delete" in operations


@pytest.mark.anyio
async def test_patch_knowledge_base_updates_business_fields(client):
    test_client, repository = client

    response = await test_client.patch(
        "/api/v1/knowledge/bases/7",
        json={
            "name": "退款与售后政策",
            "description": "退款与售后知识",
            "routing_description": "退款、售后、到账",
            "is_active": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == 7
    assert data["name"] == "退款与售后政策"
    assert data["routing_description"] == "退款、售后、到账"
    assert data["is_active"] is False
    assert data["document_count"] == 2
    assert repository.base.is_active is False


@pytest.mark.anyio
async def test_patch_knowledge_base_can_clear_optional_text(client):
    test_client, repository = client

    response = await test_client.patch(
        "/api/v1/knowledge/bases/7",
        json={
            "description": "",
            "routing_description": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["routing_description"] is None
    assert repository.base.description is None


@pytest.mark.anyio
async def test_patch_knowledge_base_rejects_blank_name(client):
    test_client, _ = client

    response = await test_client.patch(
        "/api/v1/knowledge/bases/7",
        json={"name": "   "},
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_delete_knowledge_base_returns_cleanup_summary(client):
    test_client, _ = client

    response = await test_client.delete(
        "/api/v1/knowledge/bases/7"
    )

    assert response.status_code == 200
    data = response.json()

    assert data == {
        "knowledge_base_id": 7,
        "deleted": True,
        "document_count": 2,
        "chunk_count": 5,
        "vector_count": 5,
        "disk_files_removed": True,
        "disk_cleanup_failures": [],
    }
