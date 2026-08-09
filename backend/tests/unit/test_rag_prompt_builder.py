from __future__ import annotations

from app.services.chat.prompt_builder import (
    PromptHistoryItem,
    RAGPromptBuilder,
)
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeSearchHit,
)


def hit(
    *,
    vector_id: str,
    document_id: int,
    document_name: str,
    chunk_index: int,
    content: str,
    similarity: float,
) -> KnowledgeSearchHit:
    return KnowledgeSearchHit(
        vector_id=vector_id,
        knowledge_base_id=7,
        document_id=document_id,
        document_name=document_name,
        chunk_index=chunk_index,
        content=content,
        similarity=similarity,
        distance=1.0 - similarity,
        metadata={},
    )


def test_prompt_orders_sources_by_similarity():
    builder = RAGPromptBuilder(
        max_context_chars=5000
    )

    result = builder.build(
        question="退款多久到账？",
        history=[],
        hits=[
            hit(
                vector_id="low",
                document_id=2,
                document_name="FAQ.md",
                chunk_index=0,
                content="低相关内容",
                similarity=0.60,
            ),
            hit(
                vector_id="high",
                document_id=1,
                document_name="退款政策.txt",
                chunk_index=1,
                content="审核通过后三个工作日原路退回。",
                similarity=0.91,
            ),
        ],
    )

    assert result.sources[0].vector_id == "high"
    assert result.sources[0].rank == 1
    assert "[来源1]" in result.messages[-1].content
    assert "退款政策.txt" in result.messages[-1].content


def test_prompt_carries_valid_history_before_current_question():
    builder = RAGPromptBuilder(
        max_context_chars=5000
    )

    result = builder.build(
        question="那超过三天呢？",
        history=[
            PromptHistoryItem(
                role="user",
                content="退款多久？",
            ),
            PromptHistoryItem(
                role="assistant",
                content="通常三个工作日。",
            ),
        ],
        hits=[
            hit(
                vector_id="v1",
                document_id=1,
                document_name="退款政策.txt",
                chunk_index=0,
                content="超过预计时间请联系人工客服。",
                similarity=0.88,
            )
        ],
    )

    assert [item.role for item in result.messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "那超过三天呢？" in result.messages[-1].content


def test_prompt_ignores_invalid_history_roles():
    builder = RAGPromptBuilder(
        max_context_chars=5000
    )

    result = builder.build(
        question="退款呢？",
        history=[
            PromptHistoryItem(
                role="system",
                content="不应进入历史",
            ),
            PromptHistoryItem(
                role="user",
                content="上一问",
            ),
        ],
        hits=[
            hit(
                vector_id="v1",
                document_id=1,
                document_name="退款政策.txt",
                chunk_index=0,
                content="三个工作日。",
                similarity=0.90,
            )
        ],
    )

    assert [item.role for item in result.messages] == [
        "system",
        "user",
        "user",
    ]
    assert "不应进入历史" not in " ".join(
        item.content
        for item in result.messages
    )


def test_context_never_exceeds_configured_limit():
    builder = RAGPromptBuilder(
        max_context_chars=120
    )

    result = builder.build(
        question="规则？",
        history=[],
        hits=[
            hit(
                vector_id="v1",
                document_id=1,
                document_name="规则.txt",
                chunk_index=0,
                content="A" * 1000,
                similarity=0.95,
            )
        ],
    )

    assert result.context_char_count <= 120
    assert len(result.sources) == 1
    assert len(result.sources[0].content) < 1000


def test_empty_hits_are_rejected():
    builder = RAGPromptBuilder(
        max_context_chars=5000
    )

    try:
        builder.build(
            question="退款？",
            history=[],
            hits=[],
        )
    except ValueError as exc:
        assert "hits 不能为空" in str(exc)
    else:
        raise AssertionError("应拒绝空 hits")


def test_system_prompt_contains_anti_hallucination_rules():
    builder = RAGPromptBuilder(
        max_context_chars=5000
    )

    result = builder.build(
        question="退款？",
        history=[],
        hits=[
            hit(
                vector_id="v1",
                document_id=1,
                document_name="退款政策.txt",
                chunk_index=0,
                content="三个工作日。",
                similarity=0.90,
            )
        ],
    )

    system = result.messages[0].content
    assert "不得编造" in system
    assert "只能依据" in system
    assert "历史对话" in system
    assert "[来源1]" in system
