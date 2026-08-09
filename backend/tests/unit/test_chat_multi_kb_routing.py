from __future__ import annotations

from datetime import datetime

from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatSessionRecord,
)
from app.services.chat.prompt_builder import RAGPromptBuilder
from app.services.chat.streaming_answer_service import (
    ChatStreamingAnswerService,
)
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeRouteCandidate,
    KnowledgeRoutingResult,
    KnowledgeSearchHit,
)


NOW = datetime(2026, 8, 7, 18, 30, 0)


class Repo:
    def __init__(self):
        self.count = 0

    def try_consume_daily_question(
        self,
        *,
        user_id,
        daily_limit,
    ):
        del user_id, daily_limit
        self.count += 1
        return self.count

    def commit(self):
        pass

    def rollback(self):
        pass


class Sessions:
    def __init__(
        self,
        *,
        selected_knowledge_base_id=None,
    ):
        self.repository = Repo()
        self.session = ChatSessionRecord(
            id=1,
            user_id=7,
            title="新会话",
            status="active",
            selected_knowledge_base_id=(
                selected_knowledge_base_id
            ),
            last_message_at=None,
            created_at=NOW,
            updated_at=NOW,
        )

    def get_session(self, **kwargs):
        del kwargs
        return self.session

    def recent_context(self, **kwargs):
        del kwargs
        return []

    def add_user_message(
        self,
        *,
        content,
        user_id,
        intent,
        **kwargs,
    ):
        del kwargs
        return ChatMessageRecord(
            id=1,
            session_id=1,
            user_id=user_id,
            reply_to_message_id=None,
            role="user",
            content=content,
            intent=intent,
            routed_knowledge_base_id=None,
            retrieval_status=None,
            is_fallback=False,
            question_char_count=len(content),
            prompt_token_estimate=None,
            completion_token_count=None,
            follow_up_suggestions=None,
            stream_completed_at=None,
            created_at=NOW,
            updated_at=NOW,
        )


def hit(knowledge_base_id: int) -> KnowledgeSearchHit:
    return KnowledgeSearchHit(
        vector_id=f"kb{knowledge_base_id}:doc1:v1:chunk0",
        knowledge_base_id=knowledge_base_id,
        document_id=knowledge_base_id * 10,
        document_name=(
            "物流政策.txt"
            if knowledge_base_id == 2
            else "退款政策.txt"
        ),
        chunk_index=0,
        content=(
            "物流状态连续48小时未更新请联系客服。"
            if knowledge_base_id == 2
            else "退款审核通过后三个工作日内原路退回。"
        ),
        similarity=0.82,
        distance=0.18,
        metadata={},
        chunk_id=knowledge_base_id * 100,
        priority=0,
    )


class Knowledge:
    def __init__(self):
        self.route_calls = 0
        self.search_calls = 0

    def route_and_search(self, query, **kwargs):
        del query, kwargs
        self.route_calls += 1
        item = hit(2)
        return KnowledgeRoutingResult(
            knowledge_base_id=2,
            route_score=0.81,
            candidates=(
                KnowledgeRouteCandidate(
                    knowledge_base_id=2,
                    score=0.81,
                    top_similarity=0.82,
                    matched_chunks=2,
                ),
            ),
            hits=(item,),
        )

    def search(self, query, *, knowledge_base_id, **kwargs):
        del query, kwargs
        self.search_calls += 1
        return [hit(knowledge_base_id)]


class NoRouteKnowledge(Knowledge):
    def route_and_search(self, query, **kwargs):
        del query, kwargs
        self.route_calls += 1
        return KnowledgeRoutingResult(
            knowledge_base_id=None,
            route_score=None,
            candidates=(),
            hits=(),
        )


def make(
    *,
    selected_knowledge_base_id=None,
    knowledge=None,
):
    sessions = Sessions(
        selected_knowledge_base_id=(
            selected_knowledge_base_id
        )
    )
    knowledge = knowledge or Knowledge()
    service = ChatStreamingAnswerService(
        session_service=sessions,  # type: ignore[arg-type]
        knowledge_service=knowledge,  # type: ignore[arg-type]
        prompt_builder=RAGPromptBuilder(
            max_context_chars=4000
        ),
    )
    return service, knowledge


def test_unselected_session_uses_auto_route_and_scoped_hits():
    service, knowledge = make()

    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="物流48小时没更新怎么办？",
    )

    assert plan.route_mode == "auto"
    assert plan.routed_knowledge_base_id == 2
    assert plan.route_score == 0.81
    assert plan.fallback_status is None
    assert {item.knowledge_base_id for item in plan.hits} == {2}
    assert knowledge.route_calls == 1
    assert knowledge.search_calls == 1


def test_explicit_session_knowledge_base_overrides_auto_route():
    service, knowledge = make(
        selected_knowledge_base_id=1
    )

    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="物流48小时没更新怎么办？",
    )

    assert plan.route_mode == "manual"
    assert plan.routed_knowledge_base_id == 1
    assert plan.route_score is None
    assert {item.knowledge_base_id for item in plan.hits} == {1}
    assert knowledge.route_calls == 0
    assert knowledge.search_calls == 1


def test_no_route_candidate_uses_safe_empty_fallback():
    service, knowledge = make(
        knowledge=NoRouteKnowledge()
    )

    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="今天心情怎么样？",
    )

    assert plan.route_mode == "none"
    assert plan.routed_knowledge_base_id is None
    assert plan.route_score is None
    assert plan.fallback_status == "empty"
    assert plan.hits == ()
    assert knowledge.route_calls == 1
