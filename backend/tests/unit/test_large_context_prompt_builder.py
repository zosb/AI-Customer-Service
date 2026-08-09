from __future__ import annotations

from app.services.chat.prompt_builder import RAGPromptBuilder
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeSearchHit,
)
from app.services.rag.context_guard import LargeContextGuard


def hit(
    vector_id: str,
    document_id: int,
    content: str,
    *,
    similarity: float,
    priority: int = 0,
) -> KnowledgeSearchHit:
    return KnowledgeSearchHit(
        vector_id=vector_id,
        knowledge_base_id=1,
        document_id=document_id,
        document_name=f"doc-{document_id}.txt",
        chunk_index=0,
        content=content,
        similarity=similarity,
        distance=1.0 - similarity,
        metadata={},
        priority=priority,
    )


def test_prompt_contains_layered_evidence_and_required_ranks() -> None:
    context_guard = LargeContextGuard(
        max_context_chars=2000,
        max_sources=4,
        max_chunks_per_document=2,
        critical_priority=5,
        critical_source_limit=2,
        rule_sentences_per_source=2,
        support_sentences_per_source=1,
    )
    builder = RAGPromptBuilder(
        max_context_chars=2000,
        context_guard=context_guard,
    )

    result = builder.build(
        question="高风险退款多久能到账？",
        history=[],
        hits=[
            hit(
                "normal",
                1,
                "退款通常三个工作日到账。",
                similarity=0.95,
            ),
            hit(
                "critical",
                2,
                "高风险退款必须人工复核，不得承诺即时到账。",
                similarity=0.65,
                priority=10,
            ),
        ],
    )

    prompt = result.messages[-1].content
    assert "【A层：关键业务规则" in prompt
    assert "【B层：直接回答证据】" in prompt
    assert result.sources[0].vector_id == "critical"
    assert result.required_source_ranks == (1,)
    assert "必须覆盖的关键来源：[来源1]" in prompt
