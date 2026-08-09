from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.knowledge.knowledge_upload_service import (
    KnowledgeUploadError,
    KnowledgeUploadService,
)


class FakeVectorStore:
    def __init__(self) -> None:
        self.rows = {
            "v1": {
                "document": "退款规则 A",
                "metadata": {"knowledge_base_id": 7},
                "embedding": [0.1, 0.2],
            },
            "v2": {
                "document": "退款规则 B",
                "metadata": {"knowledge_base_id": 7},
                "embedding": [0.3, 0.4],
            },
        }

    def get(self, ids):
        existing = [
            item for item in ids if item in self.rows
        ]
        return {
            "ids": existing,
            "documents": [
                self.rows[item]["document"]
                for item in existing
            ],
            "metadatas": [
                self.rows[item]["metadata"]
                for item in existing
            ],
            "embeddings": [
                self.rows[item]["embedding"]
                for item in existing
            ],
        }

    def delete(self, *, ids):
        for item in ids:
            self.rows.pop(item, None)

    def upsert(
        self,
        *,
        ids,
        embeddings,
        documents,
        metadatas,
    ):
        for item_id, embedding, document, metadata in zip(
            ids,
            embeddings,
            documents,
            metadatas,
            strict=True,
        ):
            self.rows[item_id] = {
                "document": document,
                "metadata": metadata,
                "embedding": embedding,
            }


class FakeIngestionService:
    def __init__(self) -> None:
        self.vector_store = FakeVectorStore()


class FakeRepository:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.base = SimpleNamespace(
            id=7,
            is_active=True,
            deleted_at=None,
        )
        self.documents = [
            SimpleNamespace(
                id=11,
                stored_name="kb7-a.txt",
                deleted_at=None,
            ),
            SimpleNamespace(
                id=12,
                stored_name="kb7-b.txt",
                deleted_at=None,
            ),
        ]
        self.chunks = [
            SimpleNamespace(vector_id="v1"),
            SimpleNamespace(vector_id="v2"),
        ]
        self.fail_commit = fail_commit
        self.rollback_calls = 0

    def get_base_for_management(self, knowledge_base_id: int):
        assert knowledge_base_id == 7
        return self.base

    def list_documents_for_base_delete(self, knowledge_base_id: int):
        assert knowledge_base_id == 7
        return self.documents

    def get_chunks_for_base_delete(self, knowledge_base_id: int):
        assert knowledge_base_id == 7
        return self.chunks

    def soft_delete_documents(self, documents):
        for item in documents:
            item.deleted_at = "deleted"

    def soft_delete_base(self, knowledge_base):
        knowledge_base.is_active = False
        knowledge_base.deleted_at = "deleted"

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("mysql commit failed")

    def rollback(self):
        self.rollback_calls += 1
        self.base.is_active = True
        self.base.deleted_at = None
        for item in self.documents:
            item.deleted_at = None


def build_service(
    tmp_path: Path,
    *,
    fail_commit: bool = False,
):
    repository = FakeRepository(fail_commit=fail_commit)
    ingestion = FakeIngestionService()
    service = KnowledgeUploadService(
        repository=repository,  # type: ignore[arg-type]
        ingestion_service=ingestion,  # type: ignore[arg-type]
        upload_dir=tmp_path / "uploads",
    )

    for document in repository.documents:
        (service.upload_dir / document.stored_name).write_text(
            "test",
            encoding="utf-8",
        )

    return service, repository, ingestion


def test_delete_knowledge_base_cleans_mysql_chroma_and_disk(
    tmp_path: Path,
) -> None:
    service, repository, ingestion = build_service(tmp_path)

    result = service.delete_knowledge_base(7)

    assert result.knowledge_base_id == 7
    assert result.document_count == 2
    assert result.chunk_count == 2
    assert result.vector_count == 2
    assert result.disk_files_removed is True
    assert result.disk_cleanup_failures == ()

    assert repository.base.is_active is False
    assert repository.base.deleted_at == "deleted"
    assert all(
        item.deleted_at == "deleted"
        for item in repository.documents
    )
    assert ingestion.vector_store.rows == {}
    assert list(service.upload_dir.iterdir()) == []


def test_delete_knowledge_base_restores_vectors_and_files_on_db_failure(
    tmp_path: Path,
) -> None:
    service, repository, ingestion = build_service(
        tmp_path,
        fail_commit=True,
    )

    with pytest.raises(
        KnowledgeUploadError,
        match="mysql commit failed",
    ):
        service.delete_knowledge_base(7)

    assert repository.rollback_calls == 1
    assert repository.base.is_active is True
    assert repository.base.deleted_at is None
    assert all(
        item.deleted_at is None
        for item in repository.documents
    )

    assert set(ingestion.vector_store.rows) == {"v1", "v2"}
    assert (
        service.upload_dir / "kb7-a.txt"
    ).exists()
    assert (
        service.upload_dir / "kb7-b.txt"
    ).exists()
    assert not list(
        service.upload_dir.glob(".kb-delete-*")
    )
