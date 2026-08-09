from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from app.core.config import get_settings
from app.repositories.knowledge_repository import (
    KnowledgeRepository,
)
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeIngestionError,
    KnowledgeIngestionResult,
    KnowledgeIngestionService,
)


class KnowledgeUploadError(RuntimeError):
    """知识文档上传业务失败。"""


class DuplicateKnowledgeDocumentError(KnowledgeUploadError):
    """同一知识库内已存在相同内容的有效文档。"""

    def __init__(
        self,
        *,
        existing_document_id: int,
        existing_name: str,
    ) -> None:
        self.existing_document_id = existing_document_id
        self.existing_name = existing_name
        super().__init__(
            "知识库中已存在相同内容的文档："
            f"id={existing_document_id}，name={existing_name}"
        )


@dataclass(frozen=True)
class KnowledgeUploadResult:
    ingestion: KnowledgeIngestionResult
    saved_path: Path
    sha256: str
    file_size_bytes: int




@dataclass(frozen=True)
class KnowledgeBaseDeleteResult:
    knowledge_base_id: int
    document_count: int
    chunk_count: int
    vector_count: int
    disk_files_removed: bool
    disk_cleanup_failures: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeDeleteResult:
    document_id: int
    stored_name: str
    disk_file_removed: bool


class KnowledgeUploadService:
    """
    浏览器上传文件进入知识库之前的业务层。

    负责：
    - 安全文件名；
    - 扩展名校验；
    - 流式写盘与大小限制；
    - SHA256 去重；
    - 临时文件原子改名；
    - 调用 MySQL + Chroma 入库链路；
    - 删除文档时同步清理磁盘文件。
    """

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        ingestion_service: KnowledgeIngestionService,
        upload_dir: str | Path | None = None,
    ) -> None:
        settings = get_settings()
        self.repository = repository
        self.ingestion_service = ingestion_service
        self.settings = settings
        self.upload_dir = Path(
            upload_dir or settings.upload_dir
        ).resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def upload(
        self,
        stream: BinaryIO,
        *,
        original_name: str,
        knowledge_base_id: int,
        uploaded_by: int | None = None,
        priority: int = 0,
    ) -> KnowledgeUploadResult:
        self.repository.get_active_base(knowledge_base_id)

        safe_name = self._safe_original_name(original_name)
        extension = Path(safe_name).suffix.lower()
        self._validate_extension(extension)

        token = uuid4().hex
        temporary_path = self.upload_dir / f".{token}.uploading"
        stored_name = (
            f"kb{knowledge_base_id}-{token}{extension}"
        )
        final_path = self._resolve_stored_path(stored_name)

        digest = sha256()
        written = 0
        max_bytes = (
            self.settings.max_upload_size_mb
            * 1024
            * 1024
        )

        try:
            with temporary_path.open("xb") as target:
                while True:
                    block = stream.read(1024 * 1024)
                    if block in (b"", None):
                        break
                    if not isinstance(block, bytes):
                        raise KnowledgeUploadError(
                            "上传流必须返回 bytes"
                        )

                    written += len(block)
                    if written > max_bytes:
                        raise KnowledgeUploadError(
                            "文件超过 "
                            f"{self.settings.max_upload_size_mb} MB 限制"
                        )

                    digest.update(block)
                    target.write(block)

            if written == 0:
                raise KnowledgeUploadError("上传文件不能为空")

            file_hash = digest.hexdigest()

            duplicate = (
                self.repository.find_active_duplicate_document(
                    knowledge_base_id=knowledge_base_id,
                    sha256=file_hash,
                )
            )
            if duplicate is not None:
                raise DuplicateKnowledgeDocumentError(
                    existing_document_id=duplicate.id,
                    existing_name=duplicate.original_name,
                )

            os.replace(temporary_path, final_path)

            try:
                ingestion = (
                    self.ingestion_service.ingest_document(
                        final_path,
                        knowledge_base_id=knowledge_base_id,
                        original_name=safe_name,
                        stored_name=stored_name,
                        uploaded_by=uploaded_by,
                        priority=priority,
                    )
                )
            except KnowledgeIngestionError as exc:
                # ingest_document 已负责：
                # processing -> failed，并清理可能写入的 Chroma 向量。
                # 保留原文件，便于展示失败状态、排错或后续人工重试。
                raise KnowledgeUploadError(str(exc)) from exc

            return KnowledgeUploadResult(
                ingestion=ingestion,
                saved_path=final_path,
                sha256=file_hash,
                file_size_bytes=written,
            )
        except Exception:
            if temporary_path.exists():
                temporary_path.unlink()
            raise

    def delete_document(
        self,
        document_id: int,
    ) -> KnowledgeDeleteResult:
        document = self.repository.get_document_for_delete(
            document_id
        )
        stored_name = document.stored_name
        stored_path = self._resolve_stored_path(stored_name)

        # 先执行业务删除：Chroma 清除 + MySQL 软删除。
        self.ingestion_service.delete_document(document_id)

        removed = False
        try:
            if stored_path.exists():
                stored_path.unlink()
                removed = True
        except OSError as exc:
            raise KnowledgeUploadError(
                "文档业务数据已删除，但磁盘文件删除失败："
                f"{stored_path}"
            ) from exc

        return KnowledgeDeleteResult(
            document_id=document_id,
            stored_name=stored_name,
            disk_file_removed=removed,
        )

    def delete_knowledge_base(
        self,
        knowledge_base_id: int,
    ) -> KnowledgeBaseDeleteResult:
        """
        级联删除一个知识库。

        删除语义：
        - MySQL：KnowledgeBase / KnowledgeDocument 软删除；
        - Chroma：删除该知识库仍有效文档的全部向量；
        - 磁盘：删除对应上传文件；
        - KnowledgeChunk 保留用于数据库审计，但因 Base/Document 已软删除，
          不再进入 RAG 检索。

        为避免半删除：
        1. 磁盘文件先原子移动为临时 tombstone；
        2. Chroma 删除前保留可恢复备份；
        3. MySQL 提交失败时恢复 Chroma 与磁盘文件；
        4. MySQL 提交成功后再永久清理 tombstone。
        """
        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")

        knowledge_base = self.repository.get_base_for_management(
            knowledge_base_id
        )
        documents = self.repository.list_documents_for_base_delete(
            knowledge_base_id
        )
        chunks = self.repository.get_chunks_for_base_delete(
            knowledge_base_id
        )

        vector_ids = list(
            dict.fromkeys(
                chunk.vector_id
                for chunk in chunks
                if getattr(chunk, "vector_id", None)
            )
        )

        staged_files: list[tuple[Path, Path]] = []
        vector_backup: dict[str, Any] | None = None

        try:
            # 先把正式上传文件原子改名为 tombstone。
            # 此时尚未修改 DB，如失败可直接恢复。
            for document in documents:
                stored_name = str(document.stored_name or "")
                if not stored_name:
                    continue

                original_path = self._resolve_stored_path(stored_name)
                if not original_path.exists():
                    continue

                tombstone = self._resolve_stored_path(
                    f".kb-delete-{uuid4().hex}-{stored_name}"
                )
                os.replace(original_path, tombstone)
                staged_files.append((original_path, tombstone))

            if vector_ids:
                vector_backup = self.ingestion_service.vector_store.get(
                    vector_ids
                )
                self.ingestion_service.vector_store.delete(
                    ids=vector_ids
                )

            self.repository.soft_delete_documents(documents)
            self.repository.soft_delete_base(knowledge_base)
            self.repository.commit()
        except Exception as exc:
            self.repository.rollback()

            if vector_backup is not None:
                try:
                    self._restore_vector_backup(vector_backup)
                except Exception:
                    pass

            self._restore_staged_files(staged_files)

            if isinstance(exc, KnowledgeUploadError):
                raise
            raise KnowledgeUploadError(
                f"知识库删除失败：{knowledge_base_id}：{exc}"
            ) from exc

        cleanup_failures: list[str] = []
        for _, tombstone in staged_files:
            try:
                if tombstone.exists():
                    tombstone.unlink()
            except OSError:
                cleanup_failures.append(tombstone.name)

        return KnowledgeBaseDeleteResult(
            knowledge_base_id=knowledge_base_id,
            document_count=len(documents),
            chunk_count=len(chunks),
            vector_count=len(vector_ids),
            disk_files_removed=not cleanup_failures,
            disk_cleanup_failures=tuple(cleanup_failures),
        )

    def _restore_vector_backup(
        self,
        backup: dict[str, Any],
    ) -> None:
        ids = list(backup.get("ids") or [])
        if not ids:
            return

        embeddings = backup.get("embeddings")
        if embeddings is None:
            raise KnowledgeUploadError(
                "Chroma 删除补偿失败：备份缺少 embeddings"
            )

        self.ingestion_service.vector_store.upsert(
            ids=ids,
            embeddings=list(embeddings),
            documents=list(backup.get("documents") or []),
            metadatas=list(backup.get("metadatas") or []),
        )

    @staticmethod
    def _restore_staged_files(
        staged_files: list[tuple[Path, Path]],
    ) -> None:
        for original_path, tombstone in reversed(staged_files):
            try:
                if tombstone.exists() and not original_path.exists():
                    os.replace(tombstone, original_path)
            except OSError:
                # 原始异常优先；残留 tombstone 可由运维人工清理。
                pass

    def _resolve_stored_path(
        self,
        stored_name: str,
    ) -> Path:
        if not stored_name:
            raise KnowledgeUploadError(
                "stored_name 不能为空"
            )

        candidate = (
            self.upload_dir / stored_name
        ).resolve()

        if candidate.parent != self.upload_dir:
            raise KnowledgeUploadError(
                "非法 stored_name 路径"
            )

        return candidate

    def _validate_extension(
        self,
        extension: str,
    ) -> None:
        if (
            extension
            not in self.settings.allowed_document_extensions
        ):
            raise KnowledgeUploadError(
                f"不支持的文档类型：{extension or '无扩展名'}"
            )

    @staticmethod
    def _safe_original_name(
        original_name: str,
    ) -> str:
        normalized = original_name.strip().replace("\\", "/")
        safe_name = normalized.rsplit("/", 1)[-1].strip()

        if safe_name in {"", ".", ".."}:
            raise KnowledgeUploadError("上传文件名无效")

        if "\x00" in safe_name:
            raise KnowledgeUploadError("上传文件名包含非法字符")

        # 数据库 original_name 为 VARCHAR(255)。
        if len(safe_name) > 255:
            raise KnowledgeUploadError(
                "上传文件名不能超过 255 个字符"
            )

        return safe_name
