from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeIngestionError,
    KnowledgeIngestionService,
)
from app.services.vector.chroma_store import SearchResult


class FakeRepository:
    def __init__(self) -> None:
        self.document = SimpleNamespace(
            id=42,
            content_version=1,
            original_name="政策.txt",
            deleted_at=None,
            status="processing",
        )
        self.added_chunks = []
        self.failed = None
        self.ready = None
        self.commits = 0
        self.rollbacks = 0
        self.retrievable = {}

    def get_active_base(self, knowledge_base_id: int):
        return SimpleNamespace(id=knowledge_base_id)

    def create_processing_document(self, **kwargs):
        return self.document

    def add_chunks(self, chunks):
        self.added_chunks = list(chunks)

    def mark_document_ready(self, document, *, chunk_count: int):
        self.ready = chunk_count
        document.status = "ready"

    def mark_document_failed(self, document_id: int, *, error_message: str):
        self.failed = (document_id, error_message)

    def get_retrievable_chunks_by_vector_ids(self, vector_ids):
        return {
            item: self.retrievable[item]
            for item in vector_ids
            if item in self.retrievable
        }

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeVectorStore:
    def __init__(self) -> None:
        self.upserted = None
        self.deleted = []
        self.query_results = []

    def upsert(self, **kwargs):
        self.upserted = kwargs

    def delete(self, *, ids=None, where=None):
        self.deleted.append((list(ids or []), where))

    def query(self, **kwargs):
        return list(self.query_results)


class FakeEmbeddingService:
    def embed_text(self, text: str):
        return [1.0, 0.0, 0.0, 0.0]


@pytest.fixture
def service():
    repository = FakeRepository()
    vector_store = FakeVectorStore()
    return KnowledgeIngestionService(
        repository=repository,  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
    )


def test_hash_text_is_stable() -> None:
    first = KnowledgeIngestionService._hash_text("退款政策")
    second = KnowledgeIngestionService._hash_text("退款政策")
    assert first == second
    assert len(first) == 64


def test_mime_types_match_supported_extensions() -> None:
    assert KnowledgeIngestionService._guess_mime_type(".txt") == "text/plain"
    assert KnowledgeIngestionService._guess_mime_type(".md") == "text/markdown"
    assert KnowledgeIngestionService._guess_mime_type(".pdf") == "application/pdf"


def test_vector_ids_include_mysql_document_identity() -> None:
    embedded = SimpleNamespace(
        chunks=(
            SimpleNamespace(chunk=SimpleNamespace(index=0)),
            SimpleNamespace(chunk=SimpleNamespace(index=1)),
        )
    )
    ids = KnowledgeIngestionService._build_vector_ids(
        knowledge_base_id=7,
        document_id=23,
        content_version=2,
        embedded=embedded,  # type: ignore[arg-type]
    )
    assert ids == [
        "kb7:doc23:v2:chunk0",
        "kb7:doc23:v2:chunk1",
    ]


def test_search_applies_similarity_threshold_and_mysql_guard(service) -> None:
    repository = service.repository
    vector_store = service.vector_store

    good_chunk = SimpleNamespace(
        id=41,
        knowledge_base_id=9,
        chunk_index=0,
        content_text="退款审核通过后三个工作日内原路退回。",
        priority=0,
    )
    good_document = SimpleNamespace(
        id=42,
        original_name="退款政策.txt",
    )
    repository.retrievable = {
        "good": (good_chunk, good_document),
    }
    vector_store.query_results = [
        SearchResult(
            id="good",
            document=good_chunk.content_text,
            metadata={"knowledge_base_id": 9},
            distance=0.2,
            similarity=0.8,
        ),
        SearchResult(
            id="low",
            document="无关内容",
            metadata={"knowledge_base_id": 9},
            distance=0.7,
            similarity=0.3,
        ),
        SearchResult(
            id="stale",
            document="数据库已不可检索的旧向量",
            metadata={"knowledge_base_id": 9},
            distance=0.1,
            similarity=0.9,
        ),
    ]

    hits = service.search(
        "退款多久能到账",
        knowledge_base_id=9,
        top_k=5,
        similarity_threshold=0.55,
    )

    assert len(hits) == 1
    assert hits[0].vector_id == "good"
    assert hits[0].chunk_id == 41
    assert hits[0].priority == 0
    assert hits[0].document_name == "退款政策.txt"
    assert hits[0].similarity == pytest.approx(0.8)


def test_search_rejects_invalid_threshold(service) -> None:
    with pytest.raises(ValueError, match="similarity_threshold"):
        service.search(
            "退款",
            knowledge_base_id=1,
            similarity_threshold=1.2,
        )


def test_invalid_extension_is_rejected_before_mysql_write(
    service,
    tmp_path: Path,
) -> None:
    path = tmp_path / "danger.exe"
    path.write_bytes(b"not-a-document")

    with pytest.raises(ValueError, match="不支持的文档类型"):
        service.ingest_document(path, knowledge_base_id=1)
