from pathlib import Path

from app.services.knowledge.document_embedding_pipeline import (
    embed_processed_document,
    process_and_embed_document,
)
from app.services.knowledge.document_pipeline import (
    ProcessedDocument,
)
from app.services.knowledge.document_parser import (
    ParsedDocument,
)
from app.services.knowledge.document_chunker import (
    DocumentChunk,
)


class FakeEmbeddingService:
    def __init__(self, dimension: int = 4) -> None:
        self.dimension = dimension
        self.received_texts: list[str] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.received_texts = list(texts)
        return [
            [float(index + 1)] * self.dimension
            for index, _ in enumerate(texts)
        ]


def build_processed_document() -> ProcessedDocument:
    document = ParsedDocument(
        source_path=Path("D:/test/knowledge.txt"),
        file_name="knowledge.txt",
        extension=".txt",
        text="第一块内容。第二块内容。",
        char_count=12,
        page_count=None,
    )

    chunks = (
        DocumentChunk(
            index=0,
            text="第一块内容。",
            char_count=6,
            start_char=0,
            end_char=6,
            source_name="knowledge.txt",
            source_extension=".txt",
        ),
        DocumentChunk(
            index=1,
            text="第二块内容。",
            char_count=6,
            start_char=6,
            end_char=12,
            source_name="knowledge.txt",
            source_extension=".txt",
        ),
    )

    return ProcessedDocument(
        document=document,
        chunks=chunks,
    )


def test_embed_processed_document_maps_vectors_to_chunks() -> None:
    processed = build_processed_document()
    service = FakeEmbeddingService(dimension=4)

    result = embed_processed_document(
        processed,
        embedding_service=service,  # type: ignore[arg-type]
    )

    assert result.chunk_count == 2
    assert result.embedding_dimension == 4
    assert service.received_texts == [
        "第一块内容。",
        "第二块内容。",
    ]
    assert result.chunks[0].chunk.index == 0
    assert result.chunks[0].embedding == (
        1.0,
        1.0,
        1.0,
        1.0,
    )
    assert result.chunks[1].chunk.index == 1
    assert result.chunks[1].embedding == (
        2.0,
        2.0,
        2.0,
        2.0,
    )


def test_process_and_embed_document_runs_full_pipeline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "售后知识.txt"
    path.write_text(
        "退款申请审核通过后会原路退回。" * 40,
        encoding="utf-8",
    )
    service = FakeEmbeddingService(dimension=8)

    result = process_and_embed_document(
        path,
        chunk_size=100,
        overlap=20,
        embedding_service=service,  # type: ignore[arg-type]
    )

    assert result.chunk_count > 1
    assert result.embedding_dimension == 8
    assert len(service.received_texts) == result.chunk_count
    assert all(
        embedded.chunk.source_name == "售后知识.txt"
        for embedded in result.chunks
    )
    assert all(
        embedded.dimension == 8
        for embedded in result.chunks
    )
