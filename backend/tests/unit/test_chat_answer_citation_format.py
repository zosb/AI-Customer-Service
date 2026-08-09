from __future__ import annotations

from app.services.chat.answer_service import ChatAnswerService
from app.services.llm.chat_service import ChatGenerationResult


def result(content: str) -> ChatGenerationResult:
    return ChatGenerationResult(
        content=content,
        model="qwen3.5:4b",
        prompt_token_count=10,
        completion_token_count=5,
        total_duration_ns=None,
        load_duration_ns=None,
    )


def test_source_citation_with_space_is_normalized():
    value = ChatAnswerService._normalize_model_answer(
        result("三个工作日内到账 [来源 1]。")
    )
    assert value == "三个工作日内到账 [来源1]。"


def test_source_citation_with_extra_spaces_is_normalized():
    value = ChatAnswerService._normalize_model_answer(
        result("请参考 [ 来源  2 ]。")
    )
    assert value == "请参考 [来源2]。"


def test_full_width_source_citation_is_normalized():
    value = ChatAnswerService._normalize_model_answer(
        result("请参考【来源 3】。")
    )
    assert value == "请参考[来源3]。"


def test_single_real_source_remaps_hallucinated_source_numbers():
    value = ChatAnswerService._sanitize_source_citations(
        "三个工作日 [来源1][来源2]。请联系客服 [来源3]。",
        valid_ranks=[1],
    )
    assert value == "三个工作日 [来源1]。请联系客服 [来源1]。"


def test_multiple_sources_remove_nonexistent_source_numbers():
    value = ChatAnswerService._sanitize_source_citations(
        "A [来源1]，B [来源2]，C [来源3]。",
        valid_ranks=[1, 3],
    )
    assert value == "A [来源1]，B ，C [来源3]。"


def test_duplicate_real_source_citations_are_collapsed():
    value = ChatAnswerService._sanitize_source_citations(
        "退款说明 [来源1][来源1][来源1]。",
        valid_ranks=[1],
    )
    assert value == "退款说明 [来源1]。"
