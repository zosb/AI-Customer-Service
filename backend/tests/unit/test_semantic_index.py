from pathlib import Path

from app.services.knowledge.semantic_index import (
    SemanticIndexService,
)
from app.services.vector.chroma_store import (
    ChromaVectorStore,
)


class FakeEmbeddingService:
    dimension = 4

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        vectors: list[list[float]] = []

        for text in texts:
            if "退款" in text:
                vectors.append([1.0, 0.0, 0.0, 0.0])
            elif "发货" in text or "配送" in text:
                vectors.append([0.0, 1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0, 0.0])

        return vectors

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


def build_service(
    tmp_path: Path,
) -> SemanticIndexService:
    store = ChromaVectorStore(
        persist_dir=tmp_path / "chroma",
        collection_name="semantic_index_test",
    )
    return SemanticIndexService(
        vector_store=store,
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
    )


def test_index_document_writes_all_chunks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "售后政策.txt"
    path.write_text(
        (
            "退款申请审核通过后会原路退回。"
            "如果退款未到账请联系人工客服。\n"
        )
        * 20,
        encoding="utf-8",
    )
    service = build_service(tmp_path)

    indexed = service.index_document(
        path,
        document_id="doc-refund",
        knowledge_base_id=7,
        chunk_size=120,
        overlap=20,
    )

    assert indexed.document_id == "doc-refund"
    assert indexed.chunk_count > 1
    assert indexed.embedding_dimension == 4
    assert service.vector_store.count == indexed.chunk_count

    stored = service.vector_store.get(
        list(indexed.chunk_ids)
    )
    assert len(stored["ids"]) == indexed.chunk_count
    assert all(
        metadata["document_id"] == "doc-refund"
        for metadata in stored["metadatas"]
    )
    assert all(
        metadata["knowledge_base_id"] == 7
        for metadata in stored["metadatas"]
    )


def test_semantic_search_returns_refund_document(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)

    refund = tmp_path / "refund.txt"
    refund.write_text(
        "退款审核通过后会原路退回。",
        encoding="utf-8",
    )
    delivery = tmp_path / "delivery.txt"
    delivery.write_text(
        "商品付款后通常会尽快安排发货。",
        encoding="utf-8",
    )

    service.index_document(
        refund,
        document_id="refund-doc",
        knowledge_base_id=1,
    )
    service.index_document(
        delivery,
        document_id="delivery-doc",
        knowledge_base_id=1,
    )

    results = service.search(
        "退款什么时候退回来？",
        top_k=2,
        knowledge_base_id=1,
    )

    assert results
    assert (
        results[0].metadata["document_id"]
        == "refund-doc"
    )
    assert "退款" in results[0].document


def test_search_can_filter_by_knowledge_base(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)

    first = tmp_path / "kb1.txt"
    first.write_text(
        "退款规则知识库一。",
        encoding="utf-8",
    )
    second = tmp_path / "kb2.txt"
    second.write_text(
        "退款规则知识库二。",
        encoding="utf-8",
    )

    service.index_document(
        first,
        document_id="doc-1",
        knowledge_base_id=1,
    )
    service.index_document(
        second,
        document_id="doc-2",
        knowledge_base_id=2,
    )

    results = service.search(
        "退款规则",
        knowledge_base_id=2,
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].metadata["knowledge_base_id"] == 2
    assert results[0].metadata["document_id"] == "doc-2"


def test_delete_document_removes_all_chunks(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    path = tmp_path / "delete.txt"
    path.write_text(
        "退款内容。" * 100,
        encoding="utf-8",
    )

    indexed = service.index_document(
        path,
        document_id="delete-doc",
        chunk_size=80,
        overlap=10,
    )
    assert indexed.chunk_count > 1

    service.delete_document("delete-doc")

    remaining = service.vector_store.query(
        query_embedding=[1.0, 0.0, 0.0, 0.0],
        top_k=10,
        where={"document_id": "delete-doc"},
    )
    assert remaining == []
