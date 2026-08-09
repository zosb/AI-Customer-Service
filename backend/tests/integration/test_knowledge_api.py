from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_current_user,
    get_knowledge_repository,
    get_knowledge_upload_service,
)
from app.main import app
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeIngestionResult,
)
from app.services.knowledge.knowledge_upload_service import (
    DuplicateKnowledgeDocumentError,
    KnowledgeDeleteResult,
    KnowledgeUploadResult,
)


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.documents = [
            SimpleNamespace(
                id=11,
                knowledge_base_id=7,
                original_name="退款政策.txt",
                file_extension=".txt",
                mime_type="text/plain",
                file_size_bytes=1234,
                status="ready",
                error_message=None,
                chunk_count=2,
                content_version=1,
                uploaded_by=99,
                processed_at=datetime(2026, 8, 7, 6, 0, 0),
                created_at=datetime(2026, 8, 7, 5, 59, 0),
                updated_at=datetime(2026, 8, 7, 6, 0, 0),
            )
        ]

    def list_documents(
        self,
        *,
        knowledge_base_id=None,
        limit=100,
        offset=0,
    ):
        items = self.documents
        if knowledge_base_id is not None:
            items = [
                item
                for item in items
                if item.knowledge_base_id == knowledge_base_id
            ]
        return items[offset : offset + limit]

    def count_documents(
        self,
        *,
        knowledge_base_id=None,
    ) -> int:
        if knowledge_base_id is None:
            return len(self.documents)
        return sum(
            1
            for item in self.documents
            if item.knowledge_base_id == knowledge_base_id
        )

    def get_document_for_delete(self, document_id: int):
        for item in self.documents:
            if item.id == document_id:
                return item
        raise AssertionError("test document missing")


class FakeKnowledgeUploadService:
    def __init__(
        self,
        repository: FakeKnowledgeRepository,
    ) -> None:
        self.repository = repository
        self.upload_calls: list[dict[str, object]] = []
        self.delete_calls: list[int] = []
        self.duplicate = False

    def upload(self, stream, **kwargs):
        self.upload_calls.append(dict(kwargs))

        if self.duplicate:
            raise DuplicateKnowledgeDocumentError(
                existing_document_id=11,
                existing_name="退款政策.txt",
            )

        # 确认 multipart 文件确实可读。
        content = stream.read()
        assert content == b"refund knowledge"

        return KnowledgeUploadResult(
            ingestion=KnowledgeIngestionResult(
                knowledge_base_id=7,
                document_id=11,
                original_name="退款政策.txt",
                stored_name="kb7-test.txt",
                chunk_count=2,
                vector_ids=("v1", "v2"),
                embedding_dimension=1024,
                status="ready",
            ),
            saved_path=Path("D:/fake/kb7-test.txt"),
            sha256="a" * 64,
            file_size_bytes=len(content),
        )

    def delete_document(
        self,
        document_id: int,
    ) -> KnowledgeDeleteResult:
        self.delete_calls.append(document_id)
        return KnowledgeDeleteResult(
            document_id=document_id,
            stored_name="kb7-test.txt",
            disk_file_removed=True,
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    repository = FakeKnowledgeRepository()
    upload_service = FakeKnowledgeUploadService(repository)

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=99, status="active")
    )
    app.dependency_overrides[
        get_knowledge_repository
    ] = lambda: repository
    app.dependency_overrides[
        get_knowledge_upload_service
    ] = lambda: upload_service

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client, repository, upload_service

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_knowledge_openapi_paths_are_registered(
    client,
) -> None:
    test_client, _, _ = client

    response = await test_client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert "/api/v1/knowledge/documents" in paths
    assert (
        "/api/v1/knowledge/documents/{document_id}"
        in paths
    )


@pytest.mark.anyio
async def test_upload_document_returns_201(
    client,
) -> None:
    test_client, _, service = client

    response = await test_client.post(
        "/api/v1/knowledge/documents",
        data={
            "knowledge_base_id": "7",
            "priority": "3",
        },
        files={
            "file": (
                "退款政策.txt",
                b"refund knowledge",
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["document"]["id"] == 11
    assert data["document"]["status"] == "ready"
    assert data["embedding_dimension"] == 1024
    assert data["sha256"] == "a" * 64

    assert service.upload_calls[0]["uploaded_by"] == 99
    assert service.upload_calls[0]["knowledge_base_id"] == 7
    assert service.upload_calls[0]["priority"] == 3


@pytest.mark.anyio
async def test_duplicate_upload_returns_409(
    client,
) -> None:
    test_client, _, service = client
    service.duplicate = True

    response = await test_client.post(
        "/api/v1/knowledge/documents",
        data={"knowledge_base_id": "7"},
        files={
            "file": (
                "duplicate.txt",
                b"refund knowledge",
                "text/plain",
            )
        },
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["existing_document_id"] == 11


@pytest.mark.anyio
async def test_list_documents_returns_status_and_metadata(
    client,
) -> None:
    test_client, _, _ = client

    response = await test_client.get(
        "/api/v1/knowledge/documents",
        params={
            "knowledge_base_id": 7,
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["original_name"] == "退款政策.txt"
    assert data["items"][0]["status"] == "ready"
    assert data["items"][0]["chunk_count"] == 2


@pytest.mark.anyio
async def test_delete_document_returns_sync_cleanup_result(
    client,
) -> None:
    test_client, _, service = client

    response = await test_client.delete(
        "/api/v1/knowledge/documents/11"
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "document_id": 11,
        "deleted": True,
        "vector_data_deleted": True,
        "disk_file_removed": True,
    }
    assert service.delete_calls == [11]
