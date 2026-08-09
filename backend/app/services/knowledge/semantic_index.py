from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.services.knowledge.document_embedding_pipeline import (
    EmbeddedDocument,
    process_and_embed_document,
)
from app.services.llm.embedding_service import EmbeddingService
from app.services.vector.chroma_store import (
    ChromaVectorStore,
    SearchResult,
)


@dataclass(frozen=True)
class IndexedDocument:
    """一次文档索引写入结果。"""

    document_id: str
    file_name: str
    chunk_ids: tuple[str, ...]
    chunk_count: int
    embedding_dimension: int


class SemanticIndexService:
    """文档向量化、Chroma 写入和语义检索服务。"""

    def __init__(
        self,
        *,
        vector_store: ChromaVectorStore,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = (
            embedding_service or EmbeddingService()
        )

    def index_document(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
        knowledge_base_id: int | None = None,
        max_size_mb: int = 20,
        chunk_size: int = 800,
        overlap: int = 120,
    ) -> IndexedDocument:
        """解析、分块、向量化并写入 Chroma。"""
        resolved_document_id = (
            document_id.strip()
            if document_id is not None
            else uuid4().hex
        )
        if not resolved_document_id:
            raise ValueError("document_id 不能为空")

        embedded = process_and_embed_document(
            file_path,
            max_size_mb=max_size_mb,
            chunk_size=chunk_size,
            overlap=overlap,
            embedding_service=self.embedding_service,
        )

        chunk_ids = self._build_chunk_ids(
            resolved_document_id,
            embedded,
        )

        metadatas: list[dict[str, str | int]] = []

        for embedded_chunk in embedded.chunks:
            chunk = embedded_chunk.chunk
            metadata: dict[str, str | int] = {
                "document_id": resolved_document_id,
                "file_name": (
                    chunk.source_name
                    or embedded.processed.document.file_name
                ),
                "extension": (
                    chunk.source_extension
                    or embedded.processed.document.extension
                ),
                "chunk_index": chunk.index,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
            }

            if knowledge_base_id is not None:
                metadata["knowledge_base_id"] = (
                    knowledge_base_id
                )

            metadatas.append(metadata)

        self.vector_store.upsert(
            ids=chunk_ids,
            embeddings=[
                item.embedding
                for item in embedded.chunks
            ],
            documents=[
                item.chunk.text
                for item in embedded.chunks
            ],
            metadatas=metadatas,
        )

        return IndexedDocument(
            document_id=resolved_document_id,
            file_name=embedded.processed.document.file_name,
            chunk_ids=tuple(chunk_ids),
            chunk_count=embedded.chunk_count,
            embedding_dimension=embedded.embedding_dimension,
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        knowledge_base_id: int | None = None,
        document_id: str | None = None,
    ) -> list[SearchResult]:
        """将问题向量化后查询 Chroma。"""
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("检索问题不能为空")

        query_embedding = self.embedding_service.embed_text(
            normalized_query
        )

        where = self._build_where(
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
        )

        return self.vector_store.query(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where,
        )

    def delete_document(
        self,
        document_id: str,
    ) -> None:
        normalized = document_id.strip()
        if not normalized:
            raise ValueError("document_id 不能为空")

        self.vector_store.delete(
            where={"document_id": normalized},
        )

    @staticmethod
    def _build_chunk_ids(
        document_id: str,
        embedded: EmbeddedDocument,
    ) -> list[str]:
        return [
            f"{document_id}:chunk:{item.chunk.index}"
            for item in embedded.chunks
        ]

    @staticmethod
    def _build_where(
        *,
        knowledge_base_id: int | None,
        document_id: str | None,
    ) -> dict[str, object] | None:
        filters: list[dict[str, object]] = []

        if knowledge_base_id is not None:
            filters.append(
                {"knowledge_base_id": knowledge_base_id}
            )

        if document_id is not None:
            normalized = document_id.strip()
            if not normalized:
                raise ValueError("document_id 不能为空")
            filters.append({"document_id": normalized})

        if not filters:
            return None
        if len(filters) == 1:
            return filters[0]

        return {"$and": filters}
