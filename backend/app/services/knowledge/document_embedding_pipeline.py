from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.knowledge.document_chunker import DocumentChunk
from app.services.knowledge.document_pipeline import (
    ProcessedDocument,
    process_document,
)
from app.services.llm.embedding_service import EmbeddingService


@dataclass(frozen=True)
class EmbeddedChunk:
    """带向量的知识片段。"""

    chunk: DocumentChunk
    embedding: tuple[float, ...]

    @property
    def dimension(self) -> int:
        return len(self.embedding)


@dataclass(frozen=True)
class EmbeddedDocument:
    """完成解析、分块和向量化后的文档。"""

    processed: ProcessedDocument
    chunks: tuple[EmbeddedChunk, ...]

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def embedding_dimension(self) -> int:
        if not self.chunks:
            return 0
        return self.chunks[0].dimension


def embed_processed_document(
    processed: ProcessedDocument,
    *,
    embedding_service: EmbeddingService | None = None,
) -> EmbeddedDocument:
    """
    为 ProcessedDocument 的所有 Chunk 批量生成向量。
    """
    if processed.chunk_count <= 0:
        raise ValueError("ProcessedDocument 不包含可向量化 Chunk")

    service = embedding_service or EmbeddingService()
    texts = [chunk.text for chunk in processed.chunks]
    vectors = service.embed_texts(texts)

    if len(vectors) != processed.chunk_count:
        raise RuntimeError(
            "Embedding 数量与 Chunk 数量不一致"
        )

    embedded_chunks = tuple(
        EmbeddedChunk(
            chunk=chunk,
            embedding=tuple(vector),
        )
        for chunk, vector in zip(
            processed.chunks,
            vectors,
            strict=True,
        )
    )

    return EmbeddedDocument(
        processed=processed,
        chunks=embedded_chunks,
    )


def process_and_embed_document(
    file_path: str | Path,
    *,
    max_size_mb: int = 20,
    chunk_size: int = 800,
    overlap: int = 120,
    embedding_service: EmbeddingService | None = None,
) -> EmbeddedDocument:
    """
    文件 → 解析 → 分块 → 批量 Embedding。
    """
    processed = process_document(
        file_path,
        max_size_mb=max_size_mb,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    return embed_processed_document(
        processed,
        embedding_service=embedding_service,
    )
