from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeIngestionError,
    KnowledgeIngestionResult,
)
from app.services.knowledge.knowledge_upload_service import (
    DuplicateKnowledgeDocumentError,
    KnowledgeUploadError,
    KnowledgeUploadService,
)


class FakeRepository:
    def __init__(self) -> None:
        self.duplicate = None
        self.document = None
        self.active_base_calls: list[int] = []

    def get_active_base(self, knowledge_base_id: int):
        self.active_base_calls.append(knowledge_base_id)
        return SimpleNamespace(id=knowledge_base_id)

    def find_active_duplicate_document(
        self,
        *,
        knowledge_base_id: int,
        sha256: str,
    ):
        return self.duplicate

    def get_document_for_delete(self, document_id: int):
        assert self.document is not None
        return self.document


class FakeIngestionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.deleted: list[int] = []
        self.error: Exception | None = None

    def ingest_document(self, file_path, **kwargs):
        self.calls.append(
            {
                "file_path": Path(file_path),
                **kwargs,
            }
        )
        if self.error is not None:
            raise self.error

        return KnowledgeIngestionResult(
            knowledge_base_id=int(
                kwargs["knowledge_base_id"]
            ),
            document_id=123,
            original_name=str(
                kwargs["original_name"]
            ),
            stored_name=str(
                kwargs["stored_name"]
            ),
            chunk_count=2,
            vector_ids=("v1", "v2"),
            embedding_dimension=1024,
            status="ready",
        )

    def delete_document(self, document_id: int) -> None:
        self.deleted.append(document_id)


@pytest.fixture
def service(tmp_path: Path):
    repository = FakeRepository()
    ingestion = FakeIngestionService()
    upload = KnowledgeUploadService(
        repository=repository,  # type: ignore[arg-type]
        ingestion_service=ingestion,  # type: ignore[arg-type]
        upload_dir=tmp_path / "uploads",
    )
    return upload, repository, ingestion


def test_safe_filename_removes_client_path(service) -> None:
    upload, _, ingestion = service

    result = upload.upload(
        BytesIO(b"hello knowledge"),
        original_name=r"C:\fakepath\refund.txt",
        knowledge_base_id=7,
    )

    assert result.ingestion.original_name == "refund.txt"
    assert ingestion.calls[0]["original_name"] == "refund.txt"
    assert result.saved_path.exists()


def test_successful_upload_is_persisted_and_forwarded(
    service,
) -> None:
    upload, repository, ingestion = service
    payload = "退款政策内容".encode("utf-8")

    result = upload.upload(
        BytesIO(payload),
        original_name="退款政策.txt",
        knowledge_base_id=9,
        uploaded_by=88,
        priority=3,
    )

    assert repository.active_base_calls == [9]
    assert result.file_size_bytes == len(payload)
    assert len(result.sha256) == 64
    assert result.saved_path.exists()
    assert result.saved_path.read_bytes() == payload
    assert result.ingestion.status == "ready"

    call = ingestion.calls[0]
    assert call["knowledge_base_id"] == 9
    assert call["uploaded_by"] == 88
    assert call["priority"] == 3
    assert call["stored_name"] == result.saved_path.name


def test_duplicate_sha256_is_rejected_and_temp_removed(
    service,
) -> None:
    upload, repository, ingestion = service
    repository.duplicate = SimpleNamespace(
        id=55,
        original_name="已有政策.txt",
    )

    with pytest.raises(
        DuplicateKnowledgeDocumentError,
        match="已存在相同内容",
    ) as exc_info:
        upload.upload(
            BytesIO(b"duplicate"),
            original_name="again.txt",
            knowledge_base_id=1,
        )

    assert exc_info.value.existing_document_id == 55
    assert ingestion.calls == []
    assert list(upload.upload_dir.iterdir()) == []


def test_unsupported_extension_is_rejected_before_disk_write(
    service,
) -> None:
    upload, _, ingestion = service

    with pytest.raises(
        KnowledgeUploadError,
        match="不支持的文档类型",
    ):
        upload.upload(
            BytesIO(b"payload"),
            original_name="danger.exe",
            knowledge_base_id=1,
        )

    assert ingestion.calls == []
    assert list(upload.upload_dir.iterdir()) == []


def test_empty_upload_is_rejected_and_temp_removed(
    service,
) -> None:
    upload, _, ingestion = service

    with pytest.raises(
        KnowledgeUploadError,
        match="不能为空",
    ):
        upload.upload(
            BytesIO(b""),
            original_name="empty.txt",
            knowledge_base_id=1,
        )

    assert ingestion.calls == []
    assert list(upload.upload_dir.iterdir()) == []


def test_oversized_upload_is_rejected_and_temp_removed(
    service,
    monkeypatch,
) -> None:
    upload, _, ingestion = service
    monkeypatch.setattr(
        upload.settings,
        "max_upload_size_mb",
        1,
    )

    with pytest.raises(
        KnowledgeUploadError,
        match="超过 1 MB",
    ):
        upload.upload(
            BytesIO(b"x" * (1024 * 1024 + 1)),
            original_name="large.txt",
            knowledge_base_id=1,
        )

    assert ingestion.calls == []
    assert list(upload.upload_dir.iterdir()) == []


def test_ingestion_failure_keeps_final_file_for_failed_record(
    service,
) -> None:
    upload, _, ingestion = service
    ingestion.error = KnowledgeIngestionError(
        "文档入库失败：模拟错误"
    )

    with pytest.raises(
        KnowledgeUploadError,
        match="模拟错误",
    ):
        upload.upload(
            BytesIO(b"failed payload"),
            original_name="failed.txt",
            knowledge_base_id=1,
        )

    saved_files = list(upload.upload_dir.iterdir())
    assert len(saved_files) == 1
    assert saved_files[0].suffix == ".txt"
    assert not saved_files[0].name.startswith(".")


def test_delete_document_removes_business_data_and_disk_file(
    service,
) -> None:
    upload, repository, ingestion = service
    stored_name = "kb1-test.txt"
    stored_path = upload.upload_dir / stored_name
    stored_path.write_bytes(b"delete me")

    repository.document = SimpleNamespace(
        id=42,
        stored_name=stored_name,
    )

    result = upload.delete_document(42)

    assert ingestion.deleted == [42]
    assert not stored_path.exists()
    assert result.document_id == 42
    assert result.disk_file_removed is True
