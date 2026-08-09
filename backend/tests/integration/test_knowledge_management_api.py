from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_current_user,
    get_knowledge_repository,
)
from app.main import app


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        now = datetime(2026, 8, 7, 9, 30, 0)
        self.bases = [
            SimpleNamespace(
                id=7,
                name="退款政策",
                description="退款相关企业政策",
                routing_description="退款、到账、原路退回",
                is_active=True,
                created_by=99,
                created_at=now,
                updated_at=now,
            )
        ]
        self.documents_per_base = {7: 2}

    def list_knowledge_bases(self, *, limit=100, offset=0):
        return self.bases[offset : offset + limit]

    def count_knowledge_bases(self):
        return len(self.bases)

    def count_documents(self, *, knowledge_base_id=None):
        if knowledge_base_id is None:
            return sum(self.documents_per_base.values())
        return self.documents_per_base.get(knowledge_base_id, 0)

    def create_knowledge_base(
        self,
        *,
        name,
        description,
        routing_description,
        created_by,
    ):
        now = datetime(2026, 8, 7, 9, 31, 0)
        item = SimpleNamespace(
            id=8,
            name=name,
            description=description,
            routing_description=routing_description,
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.bases.insert(0, item)
        self.documents_per_base[8] = 0
        return item

    def rollback(self):
        return None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    repository = FakeKnowledgeRepository()

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=99, status="active")
    )
    app.dependency_overrides[
        get_knowledge_repository
    ] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client, repository

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_knowledge_base_openapi_paths_are_registered(client):
    test_client, _ = client

    response = await test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/v1/knowledge/bases" in paths
    assert "/api/v1/knowledge/documents" in paths


@pytest.mark.anyio
async def test_list_knowledge_bases_includes_document_count(client):
    test_client, _ = client

    response = await test_client.get("/api/v1/knowledge/bases")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1
    assert data["items"][0]["name"] == "退款政策"
    assert data["items"][0]["document_count"] == 2
    assert data["items"][0]["is_active"] is True


@pytest.mark.anyio
async def test_create_knowledge_base_returns_201(client):
    test_client, repository = client

    response = await test_client.post(
        "/api/v1/knowledge/bases",
        json={
            "name": "物流政策",
            "description": "物流与配送说明",
            "routing_description": "物流、配送、签收",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["id"] == 8
    assert data["name"] == "物流政策"
    assert data["document_count"] == 0
    assert data["created_by"] == 99
    assert repository.bases[0].name == "物流政策"


@pytest.mark.anyio
async def test_create_knowledge_base_rejects_blank_name(client):
    test_client, _ = client

    response = await test_client.post(
        "/api/v1/knowledge/bases",
        json={
            "name": "   ",
        },
    )

    assert response.status_code == 422
