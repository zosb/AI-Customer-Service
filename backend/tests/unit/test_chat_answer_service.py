from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatSessionRecord,
    MessageSourceRecord,
)
from app.services.chat.answer_service import (
    ChatAnswerService,
    DailyQuestionLimitError,
)
from app.services.chat.prompt_builder import (
    RAGPromptBuilder,
)
from app.services.chat.session_service import (
    ContextMessage,
)
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeSearchHit,
)
from app.services.llm.chat_service import (
    ChatGenerationError,
    ChatGenerationResult,
)


NOW = datetime(2026, 8, 7, 16, 0, 0)


def make_session(
    *,
    selected_kb: int | None = None,
) -> ChatSessionRecord:
    return ChatSessionRecord(
        id=1,
        user_id=7,
        title="新会话",
        status="active",
        selected_knowledge_base_id=selected_kb,
        last_message_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_message(
    *,
    message_id: int,
    role: str,
    content: str,
    user_id: int | None,
    retrieval_status: str | None = None,
    is_fallback: bool = False,
) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=message_id,
        session_id=1,
        user_id=user_id,
        reply_to_message_id=None,
        role=role,
        content=content,
        intent=None,
        routed_knowledge_base_id=None,
        retrieval_status=retrieval_status,
        is_fallback=is_fallback,
        question_char_count=(
            len(content)
            if role == "user"
            else None
        ),
        prompt_token_estimate=None,
        completion_token_count=None,
        follow_up_suggestions=None,
        stream_completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_hit() -> KnowledgeSearchHit:
    return KnowledgeSearchHit(
        vector_id="kb1:doc2:v1:chunk0",
        knowledge_base_id=1,
        document_id=2,
        document_name="退款政策.txt",
        chunk_index=0,
        content=(
            "退款审核通过后通常在三个工作日内原路退回。"
        ),
        similarity=0.82,
        distance=0.18,
        metadata={},
        chunk_id=3,
        priority=5,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.daily_allowed = True
        self.daily_count = 0
        self.commits = 0
        self.rollbacks = 0

    def try_consume_daily_question(
        self,
        *,
        user_id,
        daily_limit,
    ):
        del user_id, daily_limit
        if not self.daily_allowed:
            return None
        self.daily_count += 1
        return self.daily_count

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeSessionService:
    def __init__(
        self,
        *,
        selected_kb=None,
        history=None,
    ) -> None:
        self.repository = FakeRepository()
        self.session = make_session(
            selected_kb=selected_kb
        )
        self.history = list(history or [])
        self.messages: list[ChatMessageRecord] = []
        self.sources: list[MessageSourceRecord] = []

    def get_session(
        self,
        *,
        session_id,
        user_id,
        include_archived=True,
    ):
        del include_archived
        assert session_id == 1
        assert user_id == 7
        return self.session

    def recent_context(
        self,
        *,
        session_id,
        user_id,
        rounds,
    ):
        del session_id, user_id, rounds
        return list(self.history)

    def add_user_message(
        self,
        *,
        session_id,
        user_id,
        content,
        intent=None,
    ):
        del session_id
        message = make_message(
            message_id=len(self.messages) + 1,
            role="user",
            content=content,
            user_id=user_id,
        )
        message = replace(
            message,
            intent=intent,
        )
        self.messages.append(message)
        return message

    def add_assistant_message(self, **kwargs):
        message = make_message(
            message_id=len(self.messages) + 1,
            role="assistant",
            content=kwargs["content"],
            user_id=None,
            retrieval_status=kwargs.get(
                "retrieval_status"
            ),
            is_fallback=kwargs.get(
                "is_fallback",
                False,
            ),
        )
        message = replace(
            message,
            reply_to_message_id=kwargs.get(
                "reply_to_message_id"
            ),
            intent=kwargs.get("intent"),
            routed_knowledge_base_id=kwargs.get(
                "routed_knowledge_base_id"
            ),
            prompt_token_estimate=kwargs.get(
                "prompt_token_estimate"
            ),
            completion_token_count=kwargs.get(
                "completion_token_count"
            ),
            follow_up_suggestions=kwargs.get(
                "follow_up_suggestions"
            ),
        )
        self.messages.append(message)
        return message

    def add_message_sources(
        self,
        *,
        message_id,
        user_id,
        sources,
    ):
        del user_id
        created = []

        for item in sources:
            source = MessageSourceRecord(
                id=len(self.sources) + 1,
                message_id=message_id,
                document_id=item.document_id,
                chunk_id=item.chunk_id,
                document_name=item.document_name,
                chunk_summary=item.chunk_summary,
                distance=item.distance,
                similarity_score=item.similarity_score,
                rank=item.rank,
                created_at=NOW,
            )
            self.sources.append(source)
            created.append(source)

        return created


class FakeKnowledgeService:
    def __init__(self, hits=None) -> None:
        self.hits = (
            [make_hit()]
            if hits is None
            else hits
        )
        self.selected_calls = 0
        self.global_calls = 0
        self.last_query = None

    def search(self, query, **kwargs):
        del kwargs
        self.last_query = query
        self.selected_calls += 1
        return list(self.hits)

    def search_any(self, query, **kwargs):
        del kwargs
        self.last_query = query
        self.global_calls += 1
        return list(self.hits)


class FakeChatModel:
    def __init__(
        self,
        *,
        content=(
            "审核通过后通常三个工作日内到账。[来源1]"
        ),
        fail=False,
    ) -> None:
        self.content = content
        self.fail = fail
        self.calls = 0

    def generate(self, messages, **kwargs):
        del messages, kwargs
        self.calls += 1

        if self.fail:
            raise ChatGenerationError("offline")

        return ChatGenerationResult(
            content=self.content,
            model="qwen3.5:4b",
            prompt_token_count=100,
            completion_token_count=20,
            total_duration_ns=None,
            load_duration_ns=None,
        )


def build_service(
    *,
    selected_kb=None,
    hits=None,
    model=None,
    history=None,
):
    session = FakeSessionService(
        selected_kb=selected_kb,
        history=history,
    )
    knowledge = FakeKnowledgeService(
        hits=hits
    )
    chat_model = model or FakeChatModel()

    service = ChatAnswerService(
        session_service=session,  # type: ignore[arg-type]
        knowledge_service=knowledge,  # type: ignore[arg-type]
        chat_model=chat_model,  # type: ignore[arg-type]
        prompt_builder=RAGPromptBuilder(
            max_context_chars=4000
        ),
    )
    return (
        service,
        session,
        knowledge,
        chat_model,
    )


def test_matched_answer_saves_messages_and_sources():
    service, session, _, model = build_service()

    result = service.answer(
        session_id=1,
        user_id=7,
        question="退款多久能到账？",
    )

    assert (
        result.assistant_message.is_fallback
        is False
    )
    assert (
        result.assistant_message.retrieval_status
        == "matched"
    )
    assert result.assistant_message.intent == "refund"
    assert len(result.sources) == 1
    assert (
        result.sources[0].document_name
        == "退款政策.txt"
    )
    assert result.sources[0].chunk_id == 3
    assert model.calls == 1
    assert len(session.messages) == 2


def test_selected_knowledge_base_uses_scoped_search():
    service, _, knowledge, _ = build_service(
        selected_kb=8
    )

    service.answer(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )

    assert knowledge.selected_calls == 1
    assert knowledge.global_calls == 0


def test_unselected_session_uses_global_search():
    service, _, knowledge, _ = build_service(
        selected_kb=None
    )

    service.answer(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )

    assert knowledge.global_calls == 1
    assert knowledge.selected_calls == 0


def test_empty_retrieval_uses_fallback_without_llm():
    service, _, _, model = build_service(
        hits=[]
    )

    result = service.answer(
        session_id=1,
        user_id=7,
        question="完全无关的问题",
    )

    assert result.assistant_message.is_fallback is True
    assert (
        result.assistant_message.retrieval_status
        == "empty"
    )
    assert result.sources == ()
    assert model.calls == 0


def test_llm_failure_uses_safe_fallback():
    service, _, _, _ = build_service(
        model=FakeChatModel(fail=True)
    )

    result = service.answer(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )

    assert result.assistant_message.is_fallback is True
    assert (
        result.assistant_message.retrieval_status
        == "failed"
    )


def test_model_sentinel_is_converted_to_fallback():
    service, _, _, _ = build_service(
        model=FakeChatModel(
            content="[[NO_RELIABLE_ANSWER]]"
        )
    )

    result = service.answer(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )

    assert result.assistant_message.is_fallback is True
    assert (
        result.assistant_message.retrieval_status
        == "empty"
    )


def test_daily_limit_rejects_before_writing_message():
    service, session, _, model = build_service()
    session.repository.daily_allowed = False

    with pytest.raises(
        DailyQuestionLimitError,
        match="今日提问次数",
    ):
        service.answer(
            session_id=1,
            user_id=7,
            question="退款多久？",
        )

    assert session.messages == []
    assert model.calls == 0


def test_followup_contextual_candidate_contains_previous_user_question():
    history = [
        ContextMessage(
            role="user",
            content="退款审核通过后多久能到账？",
        ),
        ContextMessage(
            role="assistant",
            content="通常三个工作日。",
        ),
    ]

    queries = ChatAnswerService._build_retrieval_queries(
        question="如果超过这个时间呢？",
        history=history,
    )

    assert queries[0] == "如果超过这个时间呢？"
    assert len(queries) == 2
    assert "退款审核通过后多久能到账？" in queries[1]
    assert "如果超过这个时间呢？" in queries[1]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("退款什么时候到账", "refund"),
        ("怎么申请退货", "return_exchange"),
        ("快递一直没发货", "logistics"),
        ("产品有什么功能", "product"),
        ("登录密码忘了", "account"),
        ("怎么联系人工客服", "human_service"),
        ("你好", "general"),
    ],
)
def test_intent_classification(
    question,
    expected,
):
    assert (
        ChatAnswerService.classify_intent(question)
        == expected
    )


class RepairingChatModel:
    def __init__(self, repaired_content: str) -> None:
        self.calls = 0
        self.repaired_content = repaired_content

    def generate(self, messages, **kwargs):
        del messages, kwargs
        self.calls += 1
        content = (
            "三个工作日内到账。"
            if self.calls == 1
            else self.repaired_content
        )
        return ChatGenerationResult(
            content=content,
            model="qwen3.5:4b",
            prompt_token_count=100,
            completion_token_count=20,
            total_duration_ns=None,
            load_duration_ns=None,
        )


def test_missing_critical_citation_is_repaired_once():
    model = RepairingChatModel(
        "三个工作日内到账。[来源1]"
    )
    service, _, _, _ = build_service(model=model)

    result = service.answer(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )

    assert result.assistant_message.is_fallback is False
    assert "[来源1]" in result.assistant_message.content
    assert model.calls == 2


def test_guard_failure_after_repair_uses_safe_fallback():
    model = RepairingChatModel(
        "仍然没有提供任何来源引用。"
    )
    service, _, _, _ = build_service(model=model)

    result = service.answer(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )

    assert result.assistant_message.is_fallback is True
    assert result.assistant_message.retrieval_status == "failed"
    assert result.sources == ()
    assert model.calls == 2


def test_retrieval_queries_prioritize_current_question_and_keep_topic_anchor():
    history = [
        ContextMessage(
            role="user",
            content="星河智能耳机 X1 的保修期是多久？",
        ),
        ContextMessage(
            role="assistant",
            content="标准保修期为 24 个月。",
        ),
        ContextMessage(
            role="user",
            content="售后客服电话是多少？",
        ),
        ContextMessage(
            role="assistant",
            content="客服电话为 400-888-2026。",
        ),
    ]

    queries = ChatAnswerService._build_retrieval_queries(
        question="黑色型号内部产品代码是什么？",
        history=history,
    )

    assert queries[0] == "黑色型号内部产品代码是什么？"
    assert len(queries) == 2
    assert "星河智能耳机 X1 的保修期是多久？" in queries[1]
    assert "售后客服电话是多少？" in queries[1]
    assert "黑色型号内部产品代码是什么？" in queries[1]


def test_retrieval_queries_keep_older_product_anchor_for_short_followup():
    history = [
        ContextMessage(
            role="user",
            content="X1的保修期是多少？",
        ),
        ContextMessage(
            role="assistant",
            content="24个月。",
        ),
        ContextMessage(
            role="user",
            content="黑色型号内部产品代码是什么？",
        ),
        ContextMessage(
            role="assistant",
            content="XH-X1-BLK。",
        ),
    ]

    queries = ChatAnswerService._build_retrieval_queries(
        question="那30天内又有什么政策？",
        history=history,
    )

    assert queries[0] == "那30天内又有什么政策？"
    assert "X1的保修期是多少？" in queries[1]
    assert "黑色型号内部产品代码是什么？" in queries[1]
