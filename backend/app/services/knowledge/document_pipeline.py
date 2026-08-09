from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.knowledge.document_chunker import (
    DocumentChunk,
    chunk_document,
)
from app.services.knowledge.document_parser import (
    ParsedDocument,
    parse_document,
)


@dataclass(frozen=True)
class ProcessedDocument:
    """文档解析与分块后的统一结果。"""

    document: ParsedDocument
    chunks: tuple[DocumentChunk, ...]

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


def process_document(
    file_path: str | Path,
    *,
    max_size_mb: int = 20,
    chunk_size: int = 800,
    overlap: int = 120,
) -> ProcessedDocument:
    """
    执行本地文档处理流水线。

    本函数职责：
    1. 解析 TXT / Markdown / PDF；
    2. 将解析文本切分为 Chunk；
    3. 返回统一结果。

    本函数明确不负责：
    - MySQL 持久化
    - Ollama Embedding
    - Chroma 写入
    """
    document = parse_document(
        file_path,
        max_size_mb=max_size_mb,
    )
    chunks = chunk_document(
        document,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    return ProcessedDocument(
        document=document,
        chunks=tuple(chunks),
    )
