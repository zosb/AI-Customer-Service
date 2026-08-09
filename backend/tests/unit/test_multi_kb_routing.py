from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from app.services.vector.chroma_store import SearchResult


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_text(self, value: str) -> list[float]:
        self.calls.append(value)
        return [0.1, 0.2, 0.3]


class FakeRepository:
    def __init__(self) -> None:
        self.records = {
            "refund-1": (
                SimpleNamespace(
                    id=101,
                    knowledge_base_id=1,
                    chunk_index=0,
                    content_text="退款审核通过后三个工作日内原路退回。",
                    priority=10,
                ),
                SimpleNamespace(
                    id=11,
                    original_name="退款政策.txt",
                ),
            ),
            "refund-2": (
                SimpleNamespace(
                    id=102,
                    knowledge_base_id=1,
                    chunk_index=1,
                    content_text="退款超时请联系人工客服核实状态。",
                    priority=10,
                ),
                SimpleNamespace(
                    id=11,
                    original_name="退款政策.txt",
                ),
            ),
            "logistics-1": (
                SimpleNamespace(
                    id=201,
                    knowledge_base_id=2,
                    chunk_index=0,
                    content_text="物流连续48小时未更新请联系客服。",
                    priority=0,
                ),
                SimpleNamespace(
                    id=21,
                    original_name="物流政策.txt",
                ),
            ),
            "logistics-2": (
                SimpleNamespace(
                    id=202,
                    knowledge_base_id=2,
                    chunk_index=1,
                    content_text="普通订单2至5个工作日送达。",
                    priority=0,
                ),
                SimpleNamespace(
                    id=21,
                    original_name="物流政策.txt",
                ),
            ),
        }

    def get_retrievable_chunks_by_vector_ids(self, ids):
        return {
            item_id: self.records[item_id]
            for item_id in ids
            if item_id in self.records
        }

    def get_active_base(self, knowledge_base_id):
        return SimpleNamespace(id=knowledge_base_id)

    def get_active_bases_by_ids(self, knowledge_base_ids):
        profiles = {
            1: SimpleNamespace(
                id=1,
                routing_description=(
                    "退款、到账、原路退回、退款进度"
                ),
            ),
            2: SimpleNamespace(
                id=2,
                routing_description=(
                    "物流、配送、快递、签收"
                ),
            ),
        }
        return {
            item_id: profiles[item_id]
            for item_id in knowledge_base_ids
            if item_id in profiles
        }


class FakeVectorStore:
    def __init__(self) -> None:
        self.calls = []

    def query(self, *, query_embedding, top_k, where=None):
        self.calls.append(
            {
                "embedding": list(query_embedding),
                "top_k": top_k,
                "where": where,
            }
        )

        if where == {"knowledge_base_id": 1}:
            return [
                result("refund-1", 1, 0.86),
                result("refund-2", 1, 0.83),
            ]

        if where == {"knowledge_base_id": 2}:
            return [
                result("logistics-1", 2, 0.84),
                result("logistics-2", 2, 0.82),
            ]

        return [
            result("refund-1", 1, 0.86),
            result("refund-2", 1, 0.83),
            result("logistics-1", 2, 0.66),
            result("logistics-2", 2, 0.63),
        ]


def result(
    item_id: str,
    knowledge_base_id: int,
    similarity: float,
) -> SearchResult:
    return SearchResult(
        id=item_id,
        document="",
        metadata={
            "knowledge_base_id": knowledge_base_id,
        },
        distance=1.0 - similarity,
        similarity=similarity,
    )


def make_service():
    repository = FakeRepository()
    vector_store = FakeVectorStore()
    embedding = FakeEmbeddingService()

    service = KnowledgeIngestionService(
        repository=repository,  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        embedding_service=embedding,  # type: ignore[arg-type]
    )
    return service, vector_store, embedding


def test_route_and_search_embeds_once_and_scopes_final_search():
    service, vector_store, embedding = make_service()

    routing = service.route_and_search(
        "退款审核通过后多久能到账？",
        top_k=5,
        similarity_threshold=0.55,
        route_probe_top_k=20,
        route_similarity_threshold=0.35,
    )

    assert routing.knowledge_base_id == 1
    assert routing.route_score is not None
    assert len(routing.candidates) == 2
    assert routing.candidates[0].knowledge_base_id == 1
    assert routing.hits
    assert {
        item.knowledge_base_id
        for item in routing.hits
    } == {1}

    assert embedding.calls == [
        "退款审核通过后多久能到账？"
    ]
    assert len(vector_store.calls) == 2
    assert vector_store.calls[0]["where"] is None
    assert vector_store.calls[0]["top_k"] == 20
    assert vector_store.calls[1]["where"] == {
        "knowledge_base_id": 1
    }


def test_route_returns_none_when_probe_has_no_qualified_hit():
    service, vector_store, _ = make_service()

    original_query = vector_store.query

    def low_query(*, query_embedding, top_k, where=None):
        if where is None:
            return [
                result("refund-1", 1, 0.20),
                result("logistics-1", 2, 0.19),
            ]
        return original_query(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where,
        )

    vector_store.query = low_query  # type: ignore[method-assign]

    routing = service.route_and_search(
        "完全无关的问题",
        route_similarity_threshold=0.35,
    )

    assert routing.knowledge_base_id is None
    assert routing.route_score is None
    assert routing.candidates == ()
    assert routing.hits == ()


def test_route_candidate_prefers_multi_chunk_evidence_over_single_spike():
    service, _, _ = make_service()

    hits = [
        SimpleNamespace(
            knowledge_base_id=1,
            similarity=0.86,
            priority=0,
            chunk_index=0,
        ),
        SimpleNamespace(
            knowledge_base_id=1,
            similarity=0.85,
            priority=0,
            chunk_index=1,
        ),
        SimpleNamespace(
            knowledge_base_id=1,
            similarity=0.84,
            priority=0,
            chunk_index=2,
        ),
        SimpleNamespace(
            knowledge_base_id=2,
            similarity=0.90,
            priority=0,
            chunk_index=0,
        ),
    ]

    candidates = service._build_route_candidates(
        hits,  # type: ignore[arg-type]
    )

    assert candidates[0].knowledge_base_id == 1
    assert candidates[0].matched_chunks == 3

def test_routing_description_keyword_overrides_wrong_vector_winner():
    """
    回归阶段 6.8 真实环境问题：

    物流问题的全局 Chunk Probe 可能因为“状态、客服、超时”等通用语义，
    让其他已有知识库拿到更高向量分。

    管理员已经在物流知识库配置：
        routing_description = 物流、配送、快递、签收

    因此问题显式包含“物流”时，应优先路由到物流库，再在物流库内部
    做正式 Top-K 检索。
    """
    service, vector_store, embedding = make_service()

    routing = service.route_and_search(
        "物流状态连续48小时没有更新怎么办？",
        top_k=5,
        similarity_threshold=0.55,
        route_probe_top_k=20,
        route_similarity_threshold=0.35,
    )

    # FakeVectorStore 的全局 Probe 故意让退款库 0.86/0.83
    # 高于物流库 0.66/0.63；routing_description 必须修正这个误选。
    assert routing.knowledge_base_id == 2
    assert routing.candidates[0].knowledge_base_id == 2
    assert {
        item.knowledge_base_id
        for item in routing.hits
    } == {2}

    assert embedding.calls == [
        "物流状态连续48小时没有更新怎么办？"
    ]
    assert len(vector_store.calls) == 2
    assert vector_store.calls[1]["where"] == {
        "knowledge_base_id": 2
    }


def test_routing_metadata_does_not_change_vector_order_when_no_keyword_matches():
    service, _, _ = make_service()

    routing = service.route_and_search(
        "完全没有业务路由关键词的普通问题",
        top_k=5,
        similarity_threshold=0.55,
        route_probe_top_k=20,
        route_similarity_threshold=0.35,
    )

    # 无 routing_description 关键词命中时，仍按原来的向量聚合分数。
    assert routing.knowledge_base_id == 1
