from __future__ import annotations

from app.services.llm.chat_service import LLMMessage
from app.services.rag.answer_guard import AnswerEvidenceGuard


def test_all_required_sources_are_accepted() -> None:
    result = AnswerEvidenceGuard().validate(
        "退款需要审核[来源1]，到账以银行为准[来源2]。",
        required_source_ranks=(1, 2),
    )

    assert result.valid is True
    assert result.cited_ranks == (1, 2)
    assert result.missing_required_ranks == ()


def test_missing_required_source_is_detected() -> None:
    result = AnswerEvidenceGuard().validate(
        "退款需要审核[来源1]。",
        required_source_ranks=(1, 2),
    )

    assert result.valid is False
    assert result.missing_required_ranks == (2,)


def test_repair_prompt_names_only_missing_required_sources() -> None:
    messages = AnswerEvidenceGuard.build_repair_messages(
        original_messages=(
            LLMMessage(role="system", content="系统规则"),
            LLMMessage(role="user", content="退款问题"),
        ),
        draft="草稿[来源1]",
        missing_required_ranks=(2, 4),
    )

    assert messages[-2].role == "assistant"
    assert messages[-1].role == "user"
    assert "[来源2]" in messages[-1].content
    assert "[来源4]" in messages[-1].content
    assert "不得增加" in messages[-1].content
