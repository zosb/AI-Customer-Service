from pathlib import Path

import pytest

from app.services.vector.chroma_store import (
    ChromaVectorStore,
)


def build_store(
    tmp_path: Path,
    collection_name: str = "test_collection",
) -> ChromaVectorStore:
    return ChromaVectorStore(
        persist_dir=tmp_path / "chroma",
        collection_name=collection_name,
    )


def test_store_creates_persistent_directory(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    assert store.persist_dir.exists()
    assert store.count == 0


def test_upsert_and_get_round_trip(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    store.upsert(
        ids=["chunk-1", "chunk-2"],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        documents=[
            "退款政策",
            "配送政策",
        ],
        metadatas=[
            {"source": "refund.md", "chunk_index": 0},
            {"source": "delivery.md", "chunk_index": 0},
        ],
    )

    result = store.get(["chunk-1", "chunk-2"])

    assert store.count == 2
    assert set(result["ids"]) == {
        "chunk-1",
        "chunk-2",
    }
    assert set(result["documents"]) == {
        "退款政策",
        "配送政策",
    }


def test_query_returns_most_similar_document(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    store.upsert(
        ids=["refund", "delivery"],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        documents=[
            "退款审核通过后原路退回",
            "商品通常在两个工作日内发货",
        ],
        metadatas=[
            {"topic": "refund"},
            {"topic": "delivery"},
        ],
    )

    results = store.query(
        query_embedding=[0.99, 0.01, 0.0],
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].id == "refund"
    assert results[0].metadata["topic"] == "refund"
    assert results[0].similarity > 0.9


def test_query_supports_metadata_filter(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    store.upsert(
        ids=["kb1-refund", "kb2-refund"],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.99, 0.01, 0.0],
        ],
        documents=[
            "知识库一退款规则",
            "知识库二退款规则",
        ],
        metadatas=[
            {"knowledge_base_id": 1},
            {"knowledge_base_id": 2},
        ],
    )

    results = store.query(
        query_embedding=[1.0, 0.0, 0.0],
        top_k=5,
        where={"knowledge_base_id": 2},
    )

    assert len(results) == 1
    assert (
        results[0].metadata["knowledge_base_id"]
        == 2
    )


def test_delete_by_id(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    store.upsert(
        ids=["a", "b"],
        embeddings=[
            [1.0, 0.0],
            [0.0, 1.0],
        ],
        documents=["A", "B"],
        metadatas=[{"i": 1}, {"i": 2}],
    )

    store.delete(ids=["a"])

    assert store.count == 1
    assert store.get(["a"])["ids"] == []


def test_data_persists_across_client_recreation(
    tmp_path: Path,
) -> None:
    persist_dir = tmp_path / "persistent_chroma"

    first = ChromaVectorStore(
        persist_dir=persist_dir,
        collection_name="persistent_collection",
    )
    first.upsert(
        ids=["persistent-1"],
        embeddings=[[0.1, 0.2, 0.3]],
        documents=["跨客户端持久化测试"],
        metadatas=[{"source": "test.txt"}],
    )

    second = ChromaVectorStore(
        persist_dir=persist_dir,
        collection_name="persistent_collection",
    )

    assert second.count == 1
    result = second.get(["persistent-1"])
    assert result["documents"] == [
        "跨客户端持久化测试"
    ]


@pytest.mark.parametrize(
    "collection_name",
    ["", "   "],
)
def test_empty_collection_name_is_rejected(
    tmp_path: Path,
    collection_name: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="collection_name 不能为空",
    ):
        ChromaVectorStore(
            persist_dir=tmp_path / "chroma",
            collection_name=collection_name,
        )


def test_batch_lengths_must_match(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    with pytest.raises(
        ValueError,
        match="数量必须一致",
    ):
        store.upsert(
            ids=["a"],
            embeddings=[[1.0, 0.0]],
            documents=["A", "B"],
            metadatas=[{"i": 1}],
        )


def test_batch_vector_dimensions_must_match(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    with pytest.raises(
        ValueError,
        match="向量维度必须一致",
    ):
        store.upsert(
            ids=["a", "b"],
            embeddings=[
                [1.0, 0.0],
                [1.0, 0.0, 0.0],
            ],
            documents=["A", "B"],
            metadatas=[{"i": 1}, {"i": 2}],
        )


def test_delete_requires_selector(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path)

    with pytest.raises(
        ValueError,
        match="必须提供 ids 或 where",
    ):
        store.delete()
