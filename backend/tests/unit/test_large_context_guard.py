from __future__ import annotations

from dataclasses import dataclass

from app.services.rag.context_guard import LargeContextGuard


@dataclass(frozen=True)
class Hit:
    vector_id: str
    knowledge_base_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    similarity: float
    distance: float
    metadata: dict
    chunk_id: int | None = None
    priority: int = 0


def hit(
    *,
    vector_id: str,
    document_id: int,
    chunk_index: int,
    content: str,
    similarity: float = 0.8,
    priority: int = 0,
) -> Hit:
    return Hit(
        vector_id=vector_id,
        knowledge_base_id=1,
        document_id=document_id,
        document_name=f"doc-{document_id}.txt",
        chunk_index=chunk_index,
        content=content,
        similarity=similarity,
        distance=1.0 - similarity,
        metadata={},
        chunk_id=document_id * 100 + chunk_index,
        priority=priority,
    )


def guard(**overrides) -> LargeContextGuard:
    values = {
        "max_context_chars": 1800,
        "max_sources": 6,
        "max_chunks_per_document": 2,
        "critical_priority": 5,
        "critical_source_limit": 3,
        "rule_sentences_per_source": 3,
        "support_sentences_per_source": 2,
    }
    values.update(overrides)
    return LargeContextGuard(**values)


def test_duplicate_chunks_are_collapsed() -> None:
    plan = guard().plan(
        question="退款规则是什么？",
        hits=[
            hit(
                vector_id="a",
                document_id=1,
                chunk_index=0,
                content="退款必须经过审核。",
                similarity=0.70,
            ),
            hit(
                vector_id="b",
                document_id=2,
                chunk_index=0,
                content="退款必须经过审核。",
                similarity=0.90,
            ),
        ],
    )

    assert plan.input_hits == 2
    assert plan.deduplicated_hits == 1
    assert plan.selected_sources == 1
    assert plan.evidence[0].hit.vector_id == "b"


def test_same_document_chunk_count_is_limited() -> None:
    plan = guard(max_chunks_per_document=2).plan(
        question="物流怎么办？",
        hits=[
            hit(
                vector_id=f"v{i}",
                document_id=1,
                chunk_index=i,
                content=f"物流说明第{i}条。",
                similarity=0.95 - i * 0.01,
            )
            for i in range(6)
        ],
    )

    assert len(plan.evidence) == 2
    assert {
        item.hit.chunk_index for item in plan.evidence
    } == {0, 1}


def test_critical_rule_survives_many_higher_similarity_noise_hits() -> None:
    hits = [
        hit(
            vector_id=f"noise-{i}",
            document_id=i + 10,
            chunk_index=0,
            content=(
                "这是普通退款背景介绍，没有强制业务约束。"
                f"编号{i}。"
            ),
            similarity=0.99 - i * 0.005,
        )
        for i in range(20)
    ]
    hits.append(
        hit(
            vector_id="critical",
            document_id=99,
            chunk_index=0,
            content=(
                "高风险退款必须由人工复核。"
                "不得向用户承诺即时到账。"
            ),
            similarity=0.61,
            priority=10,
        )
    )

    plan = guard(max_sources=5).plan(
        question="高风险退款可以马上到账吗？",
        hits=hits,
    )

    assert plan.evidence[0].hit.vector_id == "critical"
    assert plan.evidence[0].tier == "A"
    assert plan.evidence[0].required is True
    assert "不得向用户承诺即时到账" in plan.evidence[0].content


def test_query_related_rule_sentence_is_promoted_to_a_layer() -> None:
    plan = guard().plan(
        question="物流48小时没更新怎么办？",
        hits=[
            hit(
                vector_id="logistics",
                document_id=3,
                chunk_index=0,
                content=(
                    "普通订单通常正常配送。"
                    "如果物流状态连续48小时没有更新，"
                    "需要联系人工客服核实承运状态。"
                    "仓库每天进行盘点。"
                ),
                similarity=0.72,
            )
        ],
    )

    evidence = plan.evidence[0]
    assert evidence.tier == "A"
    assert evidence.required is True
    assert "48小时" in evidence.content


def test_source_count_and_context_budget_are_enforced() -> None:
    plan = guard(
        max_sources=3,
        max_context_chars=260,
    ).plan(
        question="退款规则",
        hits=[
            hit(
                vector_id=f"v{i}",
                document_id=i + 1,
                chunk_index=0,
                content=("退款规则内容。" * 40),
                similarity=0.90 - i * 0.01,
            )
            for i in range(12)
        ],
    )

    assert plan.selected_sources <= 3
    assert plan.selected_content_chars <= 260


def test_rule_extraction_does_not_keep_whole_large_chunk() -> None:
    content = (
        "背景介绍。" * 30
        + "退款金额超过一万元必须人工复核。"
        + "更多无关背景。" * 30
    )
    plan = guard().plan(
        question="一万元以上退款怎么处理？",
        hits=[
            hit(
                vector_id="large",
                document_id=1,
                chunk_index=0,
                content=content,
                similarity=0.75,
            )
        ],
    )

    selected = plan.evidence[0].content
    assert "必须人工复核" in selected
    assert len(selected) < len(content)


def test_no_explicit_critical_rule_still_requires_top_source() -> None:
    plan = guard().plan(
        question="产品有什么特点？",
        hits=[
            hit(
                vector_id="top",
                document_id=1,
                chunk_index=0,
                content="产品支持企业知识库问答。",
                similarity=0.92,
            ),
            hit(
                vector_id="second",
                document_id=2,
                chunk_index=0,
                content="产品支持会话历史。",
                similarity=0.80,
            ),
        ],
    )

    assert plan.evidence[0].hit.vector_id == "top"
    assert plan.evidence[0].required is True
    assert plan.evidence[0].tier == "A"


def test_required_source_count_is_capped() -> None:
    plan = guard(
        critical_source_limit=2,
        max_sources=6,
    ).plan(
        question="退款必须遵守哪些规则？",
        hits=[
            hit(
                vector_id=f"critical-{i}",
                document_id=i + 1,
                chunk_index=0,
                content=f"退款规则{i}必须人工确认。",
                similarity=0.90 - i * 0.01,
                priority=10,
            )
            for i in range(5)
        ],
    )

    assert plan.required_sources == 2
    assert sum(item.required for item in plan.evidence) == 2
