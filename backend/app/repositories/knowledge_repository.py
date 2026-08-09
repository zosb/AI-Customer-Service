from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)


class KnowledgeRepositoryError(RuntimeError):
    """知识库数据库操作失败。"""


class KnowledgeRepository:
    """知识库 MySQL 持久化仓储。"""

    def __init__(self, database: Session) -> None:
        self.database = database

    def list_knowledge_bases(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeBase]:
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        if offset < 0:
            raise ValueError("offset 不能小于 0")

        return list(
            self.database.scalars(
                select(KnowledgeBase)
                .where(KnowledgeBase.deleted_at.is_(None))
                .order_by(
                    KnowledgeBase.created_at.desc(),
                    KnowledgeBase.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
        )

    def count_knowledge_bases(self) -> int:
        return int(
            self.database.scalar(
                select(func.count())
                .select_from(KnowledgeBase)
                .where(KnowledgeBase.deleted_at.is_(None))
            )
            or 0
        )

    def create_knowledge_base(
        self,
        *,
        name: str,
        description: str | None,
        routing_description: str | None,
        created_by: int | None,
    ) -> KnowledgeBase:
        knowledge_base = KnowledgeBase(
            name=name,
            description=description,
            routing_description=routing_description,
            is_active=True,
            created_by=created_by,
        )
        self.database.add(knowledge_base)
        self.database.commit()
        self.database.refresh(knowledge_base)
        return knowledge_base

    def get_base_for_management(
        self,
        knowledge_base_id: int,
    ) -> KnowledgeBase:
        """读取未删除知识库；允许读取已停用知识库用于编辑/删除。"""
        knowledge_base = self.database.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if knowledge_base is None:
            raise KnowledgeRepositoryError(
                f"知识库不存在或已删除：{knowledge_base_id}"
            )
        return knowledge_base

    def update_knowledge_base(
        self,
        knowledge_base: KnowledgeBase,
        *,
        values: dict[str, object],
    ) -> KnowledgeBase:
        """更新允许编辑的知识库字段并立即持久化。"""
        allowed = {
            "name",
            "description",
            "routing_description",
            "is_active",
        }
        unexpected = set(values) - allowed
        if unexpected:
            raise ValueError(
                "包含不允许修改的知识库字段："
                + ", ".join(sorted(unexpected))
            )

        for field_name, value in values.items():
            setattr(knowledge_base, field_name, value)

        self.database.commit()
        self.database.refresh(knowledge_base)
        return knowledge_base

    def get_active_base(self, knowledge_base_id: int) -> KnowledgeBase:
        knowledge_base = self.database.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.is_active.is_(True),
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if knowledge_base is None:
            raise KnowledgeRepositoryError(
                f"知识库不存在、已停用或已删除：{knowledge_base_id}"
            )
        return knowledge_base

    def get_active_bases_by_ids(
        self,
        knowledge_base_ids: Sequence[int],
    ) -> dict[int, KnowledgeBase]:
        """
        批量读取仍可用于 RAG 路由的知识库。

        自动路由只允许使用：
        - is_active = true
        - deleted_at is null

        返回 dict 便于路由服务按 knowledge_base_id O(1) 查询
        routing_description。
        """
        unique_ids = list(
            dict.fromkeys(
                int(item)
                for item in knowledge_base_ids
                if int(item) > 0
            )
        )
        if not unique_ids:
            return {}

        items = self.database.scalars(
            select(KnowledgeBase).where(
                KnowledgeBase.id.in_(unique_ids),
                KnowledgeBase.is_active.is_(True),
                KnowledgeBase.deleted_at.is_(None),
            )
        ).all()

        return {
            int(item.id): item
            for item in items
        }

    def find_active_duplicate_document(
        self,
        *,
        knowledge_base_id: int,
        sha256: str,
    ) -> KnowledgeDocument | None:
        """
        在同一知识库内查找相同内容的有效文档。

        failed 文档不阻止重新上传，便于修复环境后重试。
        """
        return self.database.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.sha256 == sha256,
                KnowledgeDocument.status.in_(("processing", "ready")),
                KnowledgeDocument.deleted_at.is_(None),
            )
        )

    def list_documents(
        self,
        *,
        knowledge_base_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeDocument]:
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        if offset < 0:
            raise ValueError("offset 不能小于 0")

        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.deleted_at.is_(None)
        )

        if knowledge_base_id is not None:
            statement = statement.where(
                KnowledgeDocument.knowledge_base_id
                == knowledge_base_id
            )

        statement = (
            statement.order_by(
                KnowledgeDocument.created_at.desc(),
                KnowledgeDocument.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            self.database.scalars(statement).all()
        )

    def count_documents(
        self,
        *,
        knowledge_base_id: int | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.deleted_at.is_(None))
        )

        if knowledge_base_id is not None:
            statement = statement.where(
                KnowledgeDocument.knowledge_base_id
                == knowledge_base_id
            )

        return int(self.database.scalar(statement) or 0)

    def create_processing_document(
        self,
        *,
        knowledge_base_id: int,
        original_name: str,
        stored_name: str,
        file_extension: str,
        mime_type: str | None,
        file_size_bytes: int,
        sha256: str,
        uploaded_by: int | None,
    ) -> KnowledgeDocument:
        document = KnowledgeDocument(
            knowledge_base_id=knowledge_base_id,
            original_name=original_name,
            stored_name=stored_name,
            file_extension=file_extension,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            sha256=sha256,
            status="processing",
            error_message=None,
            chunk_count=0,
            content_version=1,
            uploaded_by=uploaded_by,
        )
        self.database.add(document)
        self.database.flush()
        return document

    def add_chunks(
        self,
        chunks: Sequence[KnowledgeChunk],
    ) -> None:
        self.database.add_all(list(chunks))

    def mark_document_ready(
        self,
        document: KnowledgeDocument,
        *,
        chunk_count: int,
    ) -> None:
        document.status = "ready"
        document.error_message = None
        document.chunk_count = chunk_count
        document.processed_at = self._now_naive_utc()

    def mark_document_failed(
        self,
        document_id: int,
        *,
        error_message: str,
    ) -> None:
        document = self.database.get(KnowledgeDocument, document_id)
        if document is None:
            return
        document.status = "failed"
        document.error_message = error_message[:8000]
        document.processed_at = self._now_naive_utc()

    def get_document_for_delete(
        self,
        document_id: int,
    ) -> KnowledgeDocument:
        document = self.database.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.deleted_at.is_(None),
            )
        )
        if document is None:
            raise KnowledgeRepositoryError(
                f"知识库文档不存在或已删除：{document_id}"
            )
        return document

    def get_document_chunks(
        self,
        document_id: int,
    ) -> list[KnowledgeChunk]:
        return list(
            self.database.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == document_id)
                .order_by(KnowledgeChunk.chunk_index)
            ).all()
        )

    def get_retrievable_chunks_by_vector_ids(
        self,
        vector_ids: Sequence[str],
    ) -> dict[str, tuple[KnowledgeChunk, KnowledgeDocument]]:
        if not vector_ids:
            return {}

        rows = self.database.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .join(
                KnowledgeBase,
                KnowledgeBase.id == KnowledgeChunk.knowledge_base_id,
            )
            .where(
                KnowledgeChunk.vector_id.in_(list(vector_ids)),
                KnowledgeDocument.status == "ready",
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeBase.is_active.is_(True),
                KnowledgeBase.deleted_at.is_(None),
            )
        ).all()

        return {
            chunk.vector_id: (chunk, document)
            for chunk, document in rows
        }

    def list_documents_for_base_delete(
        self,
        knowledge_base_id: int,
    ) -> list[KnowledgeDocument]:
        """列出知识库下仍有效的全部文档，用于知识库级联删除。"""
        return list(
            self.database.scalars(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.knowledge_base_id
                    == knowledge_base_id,
                    KnowledgeDocument.deleted_at.is_(None),
                )
                .order_by(KnowledgeDocument.id)
            ).all()
        )

    def get_chunks_for_base_delete(
        self,
        knowledge_base_id: int,
    ) -> list[KnowledgeChunk]:
        """读取仍有效文档对应的全部 Chunk / vector_id。"""
        return list(
            self.database.scalars(
                select(KnowledgeChunk)
                .join(
                    KnowledgeDocument,
                    KnowledgeDocument.id
                    == KnowledgeChunk.document_id,
                )
                .where(
                    KnowledgeChunk.knowledge_base_id
                    == knowledge_base_id,
                    KnowledgeDocument.deleted_at.is_(None),
                )
                .order_by(
                    KnowledgeChunk.document_id,
                    KnowledgeChunk.chunk_index,
                )
            ).all()
        )

    def soft_delete_documents(
        self,
        documents: Sequence[KnowledgeDocument],
    ) -> None:
        deleted_at = self._now_naive_utc()
        for document in documents:
            document.deleted_at = deleted_at

    def soft_delete_base(
        self,
        knowledge_base: KnowledgeBase,
    ) -> None:
        knowledge_base.is_active = False
        knowledge_base.deleted_at = self._now_naive_utc()

    def soft_delete_document(
        self,
        document: KnowledgeDocument,
    ) -> None:
        document.deleted_at = self._now_naive_utc()

    def commit(self) -> None:
        self.database.commit()

    def rollback(self) -> None:
        self.database.rollback()

    @staticmethod
    def _now_naive_utc() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
