from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json

from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatSessionRecord,
    MessageSourceRecord,
)
from app.services.chat.streaming_answer_service import (
    ChatStreamingAnswerService,
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
    ChatStreamChunk,
)


NOW = datetime(2026, 8, 7, 16, 30, 0)


class Repo:
    def __init__(self):
        self.count = 0
    def try_consume_daily_question(
        self, *, user_id, daily_limit
    ):
        del user_id, daily_limit
        self.count += 1
        return self.count
    def commit(self):
        pass
    def rollback(self):
        pass


class Sessions:
    def __init__(self):
        self.repository = Repo()
        self.messages = []
        self.sources = []
        self.session = ChatSessionRecord(
            id=1,
            user_id=7,
            title="新会话",
            status="active",
            selected_knowledge_base_id=None,
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
        self, *, content, user_id, intent, **kwargs
    ):
        del kwargs
        msg = ChatMessageRecord(
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
        self.messages.append(msg)
        return msg

    def add_assistant_message(self, **kwargs):
        msg = ChatMessageRecord(
            id=2,
            session_id=1,
            user_id=None,
            reply_to_message_id=kwargs[
                "reply_to_message_id"
            ],
            role="assistant",
            content=kwargs["content"],
            intent=kwargs["intent"],
            routed_knowledge_base_id=kwargs[
                "routed_knowledge_base_id"
            ],
            retrieval_status=kwargs[
                "retrieval_status"
            ],
            is_fallback=kwargs["is_fallback"],
            question_char_count=None,
            prompt_token_estimate=kwargs.get(
                "prompt_token_estimate"
            ),
            completion_token_count=kwargs.get(
                "completion_token_count"
            ),
            follow_up_suggestions=kwargs.get(
                "follow_up_suggestions"
            ),
            stream_completed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        self.messages.append(msg)
        return msg

    def add_message_sources(
        self, *, message_id, sources, **kwargs
    ):
        del kwargs
        result = []
        for i, src in enumerate(sources, start=1):
            row = MessageSourceRecord(
                id=i,
                message_id=message_id,
                document_id=src.document_id,
                chunk_id=src.chunk_id,
                document_name=src.document_name,
                chunk_summary=src.chunk_summary,
                distance=src.distance,
                similarity_score=src.similarity_score,
                rank=src.rank,
                created_at=NOW,
            )
            result.append(row)
            self.sources.append(row)
        return result


class Knowledge:
    def __init__(self, hits):
        self.hits = hits

    def search_any(self, query, **kwargs):
        del query, kwargs
        return list(self.hits)

    def search(self, query, **kwargs):
        del query, kwargs
        return list(self.hits)


class Model:
    def __init__(self, *, fail=False):
        self.fail = fail

    def stream(self, messages, **kwargs):
        del messages, kwargs
        yield ChatStreamChunk(
            content="三个工作日 [来源 1][来源2][来源3]",
            done=False,
            model="qwen3.5:4b",
        )
        if self.fail:
            raise ChatGenerationError("broken")
        yield ChatStreamChunk(
            content="。",
            done=False,
            model="qwen3.5:4b",
        )
        yield ChatStreamChunk(
            content="",
            done=True,
            model="qwen3.5:4b",
            prompt_token_count=80,
            completion_token_count=9,
        )


def hit():
    return KnowledgeSearchHit(
        vector_id="kb1:doc1:v1:chunk0",
        knowledge_base_id=1,
        document_id=1,
        document_name="退款政策.txt",
        chunk_index=0,
        content="退款通常三个工作日内原路退回。",
        similarity=0.82,
        distance=0.18,
        metadata={},
        chunk_id=10,
        priority=10,
    )


def parse_event(value):
    event = None
    data = None
    for line in value.splitlines():
        if line.startswith("event: "):
            event = line[7:]
        if line.startswith("data: "):
            data = json.loads(line[6:])
    return event, data


def make(hits=None, fail=False):
    sessions = Sessions()
    service = ChatStreamingAnswerService(
        session_service=sessions,  # type: ignore[arg-type]
        knowledge_service=Knowledge(
            [hit()] if hits is None else hits
        ),  # type: ignore[arg-type]
        chat_model=Model(fail=fail),  # type: ignore[arg-type]
        prompt_builder=RAGPromptBuilder(
            max_context_chars=4000
        ),
    )
    return service, sessions


def test_success_stream_emits_meta_delta_replace_sources_done():
    service, sessions = make()
    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )
    events = [
        parse_event(item)
        for item in service.iter_sse(plan)
    ]
    names = [name for name, _ in events]

    assert names[0] == "meta"
    assert "delta" in names
    assert "replace" in names
    assert "sources" in names
    assert names[-1] == "done"

    done = events[-1][1]
    assert done["is_fallback"] is False
    assert done["content"] == "三个工作日 [来源1]。"
    assert done["source_count"] == 1
    assert sessions.sources[0].chunk_id == 10


def test_empty_retrieval_streams_fallback_without_sources():
    service, _ = make(hits=[])
    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="完全无关问题",
    )
    events = [
        parse_event(item)
        for item in service.iter_sse(plan)
    ]

    assert events[0][0] == "meta"
    assert events[-1][0] == "done"
    assert events[-1][1]["is_fallback"] is True
    assert events[-1][1]["retrieval_status"] == "empty"
    assert events[-1][1]["source_count"] == 0


def test_stream_failure_after_partial_output_uses_replace():
    service, _ = make(fail=True)
    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )
    events = [
        parse_event(item)
        for item in service.iter_sse(plan)
    ]
    names = [name for name, _ in events]

    assert "error" in names
    assert "replace" in names
    assert events[-1][0] == "done"
    assert events[-1][1]["is_fallback"] is True
    assert events[-1][1]["retrieval_status"] == "failed"


class RepairingStreamModel:
    def __init__(self, *, repair_ok=True):
        self.generate_calls = 0
        self.repair_ok = repair_ok

    def stream(self, messages, **kwargs):
        del messages, kwargs
        yield ChatStreamChunk(
            content="三个工作日内到账。",
            done=False,
            model="qwen3.5:4b",
        )
        yield ChatStreamChunk(
            content="",
            done=True,
            model="qwen3.5:4b",
            prompt_token_count=80,
            completion_token_count=8,
        )

    def generate(self, messages, **kwargs):
        del messages, kwargs
        self.generate_calls += 1
        content = (
            "三个工作日内到账。[来源1]"
            if self.repair_ok
            else "仍然没有来源引用。"
        )
        return ChatGenerationResult(
            content=content,
            model="qwen3.5:4b",
            prompt_token_count=95,
            completion_token_count=10,
            total_duration_ns=None,
            load_duration_ns=None,
        )


def test_stream_missing_required_citation_repairs_with_replace():
    sessions = Sessions()
    model = RepairingStreamModel(repair_ok=True)
    service = ChatStreamingAnswerService(
        session_service=sessions,  # type: ignore[arg-type]
        knowledge_service=Knowledge([hit()]),  # type: ignore[arg-type]
        chat_model=model,  # type: ignore[arg-type]
        prompt_builder=RAGPromptBuilder(
            max_context_chars=4000
        ),
    )

    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )
    events = [
        parse_event(item)
        for item in service.iter_sse(plan)
    ]

    replace_events = [
        data for name, data in events if name == "replace"
    ]
    assert replace_events
    assert "[来源1]" in replace_events[-1]["content"]
    assert events[-1][1]["is_fallback"] is False
    assert model.generate_calls == 1


def test_stream_guard_failure_replaces_with_safe_fallback():
    sessions = Sessions()
    model = RepairingStreamModel(repair_ok=False)
    service = ChatStreamingAnswerService(
        session_service=sessions,  # type: ignore[arg-type]
        knowledge_service=Knowledge([hit()]),  # type: ignore[arg-type]
        chat_model=model,  # type: ignore[arg-type]
        prompt_builder=RAGPromptBuilder(
            max_context_chars=4000
        ),
    )

    plan = service.prepare(
        session_id=1,
        user_id=7,
        question="退款多久？",
    )
    events = [
        parse_event(item)
        for item in service.iter_sse(plan)
    ]

    assert any(
        name == "error"
        and data["code"] == "evidence_guard_failed"
        for name, data in events
    )
    assert events[-1][1]["is_fallback"] is True
    assert events[-1][1]["retrieval_status"] == "failed"
