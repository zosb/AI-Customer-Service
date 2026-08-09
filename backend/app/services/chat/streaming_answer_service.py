from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterator, Sequence

from app.core.config import get_settings
from app.repositories.chat_repository import (
    ChatMessageRecord,
    MessageSourceRecord,
)
from app.services.chat.answer_service import (
    ChatAnswerService,
    DailyQuestionLimitError,
)
from app.services.chat.prompt_builder import (
    BuiltRAGPrompt,
    PromptHistoryItem,
    RAGPromptBuilder,
)
from app.services.chat.session_service import (
    ChatSessionService,
    ChatValidationError,
    MessageSourceInput,
)
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeIngestionService,
    KnowledgeSearchHit,
)
from app.services.llm.chat_service import (
    ChatGenerationError,
    ChatGenerationResult,
    ChatStreamChunk,
    OllamaChatService,
)
from app.services.rag.answer_guard import (
    AnswerEvidenceGuard,
)


@dataclass(frozen=True)
class ChatStreamPlan:
    session_id: int
    user_id: int
    user_message: ChatMessageRecord
    intent: str
    daily_question_count: int
    retrieval_query: str
    routed_knowledge_base_id: int | None
    route_mode: str
    route_score: float | None
    hits: tuple[KnowledgeSearchHit, ...]
    prompt: BuiltRAGPrompt | None
    fallback_status: str | None


class ChatStreamingAnswerService:
    """SSE 流式 AI 客服问答编排，包含多知识库自动路由。"""

    # Scoped retrieval rescue:
    # 仅当自动路由已可靠锁定业务知识库、常规检索没有命中时，
    # 才允许在同一个知识库内使用更宽松的相似度做一次补救检索。
    #
    # 全局 RAG 阈值仍保持 settings.rag_similarity_threshold（当前 0.55），
    # 不会把其他知识库的安全边界整体降低。
    SCOPED_RESCUE_BASE_THRESHOLD = 0.45
    SCOPED_RESCUE_MIN_ROUTE_SCORE = 0.40

    @classmethod
    def _scoped_rescue_threshold(
        cls,
        *,
        normal_threshold: float,
        route_threshold: float,
    ) -> float | None:
        """
        计算同库补救检索阈值。

        rescue 必须：
        1. 不低于知识库路由阈值；
        2. 不低于本阶段保守基线 0.45；
        3. 严格低于正常 RAG 阈值，否则没有二次检索意义。
        """
        normal = float(normal_threshold)
        route = float(route_threshold)
        rescue = max(
            route,
            cls.SCOPED_RESCUE_BASE_THRESHOLD,
        )
        if rescue >= normal:
            return None
        return rescue

    @classmethod
    def _can_attempt_scoped_rescue(
        cls,
        *,
        intent: str,
        route_score: float | None,
        route_threshold: float,
        contextual_followup: bool = False,
    ) -> bool:
        """判断自动路由后是否允许同库低阈值补救。

        普通 general 问题仍不降阈值；但真实多轮追问可能天然很短，
        例如“那30天内又有什么政策？”。当它确实带有历史上下文、且
        Router 已经较可靠地锁定某个知识库时，允许只在该知识库内
        做一次 0.45 的保守补救，不扩大到其他知识库。
        """
        if route_score is None:
            return False
        if intent == "general" and not contextual_followup:
            return False

        minimum_route_score = max(
            float(route_threshold),
            cls.SCOPED_RESCUE_MIN_ROUTE_SCORE,
        )
        if intent == "general":
            minimum_route_score = max(
                minimum_route_score,
                cls.SCOPED_RESCUE_BASE_THRESHOLD,
            )
        return float(route_score) >= minimum_route_score

    def __init__(
        self,
        *,
        session_service: ChatSessionService,
        knowledge_service: KnowledgeIngestionService,
        chat_model: OllamaChatService | None = None,
        prompt_builder: RAGPromptBuilder | None = None,
        answer_guard: AnswerEvidenceGuard | None = None,
    ) -> None:
        self.session_service = session_service
        self.knowledge_service = knowledge_service
        self.chat_model = chat_model or OllamaChatService()
        self.prompt_builder = (
            prompt_builder or RAGPromptBuilder()
        )
        self.answer_guard = (
            answer_guard or AnswerEvidenceGuard()
        )
        self.settings = get_settings()

    def prepare(
        self,
        *,
        session_id: int,
        user_id: int,
        question: str,
    ) -> ChatStreamPlan:
        """
        在 HTTP 200/SSE 响应真正开始前完成：
        权限、参数、额度、user message、RAG 检索和 Prompt 准备。
        因此 404/422/429 可由 FastAPI 正常返回。
        """
        normalized = question.strip()
        if not normalized:
            raise ChatValidationError("消息内容不能为空")
        if len(normalized) > self.settings.question_max_length:
            raise ChatValidationError(
                "单次提问不能超过 "
                f"{self.settings.question_max_length} 字"
            )

        session = self.session_service.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )

        history = self.session_service.recent_context(
            session_id=session_id,
            user_id=user_id,
            rounds=self.settings.context_history_rounds,
        )

        daily_count = self._consume_daily_quota(
            user_id=user_id
        )
        intent = ChatAnswerService.classify_intent(
            normalized
        )

        user_message = self.session_service.add_user_message(
            session_id=session_id,
            user_id=user_id,
            content=normalized,
            intent=intent,
        )

        retrieval_queries = (
            ChatAnswerService._build_retrieval_queries(
                question=normalized,
                history=history,
            )
        )
        # 第一候选始终是当前问题本身；上下文增强 Query 仅在必要时
        # 作为回退，避免“上一轮问题”稀释本轮 embedding。
        retrieval_query = retrieval_queries[0]
        contextual_followup = len(retrieval_queries) > 1
        routed_knowledge_base_id = (
            session.selected_knowledge_base_id
        )
        route_mode = (
            "manual"
            if routed_knowledge_base_id is not None
            else "auto"
        )
        route_score: float | None = None

        try:
            if routed_knowledge_base_id is not None:
                # 手动绑定知识库：范围已经由用户明确限定，因此可以
                # 安全地先尝试当前问题，再尝试上下文增强 Query。
                hits = []
                for candidate_query in retrieval_queries:
                    candidate_hits = self.knowledge_service.search(
                        candidate_query,
                        knowledge_base_id=routed_knowledge_base_id,
                        top_k=self.settings.rag_top_k,
                        similarity_threshold=(
                            self.settings.rag_similarity_threshold
                        ),
                    )
                    if candidate_hits:
                        hits = candidate_hits
                        retrieval_query = candidate_query
                        break

                # 手动知识库的业务边界最明确；正常阈值没有命中时，
                # 允许在同一库内用保守 0.45 做一次补救。
                rescue_threshold = self._scoped_rescue_threshold(
                    normal_threshold=(
                        self.settings.rag_similarity_threshold
                    ),
                    route_threshold=(
                        self.settings.rag_route_similarity_threshold
                    ),
                )
                if not hits and rescue_threshold is not None:
                    for candidate_query in retrieval_queries:
                        candidate_hits = self.knowledge_service.search(
                            candidate_query,
                            knowledge_base_id=(
                                routed_knowledge_base_id
                            ),
                            top_k=self.settings.rag_top_k,
                            similarity_threshold=rescue_threshold,
                        )
                        if candidate_hits:
                            hits = candidate_hits
                            retrieval_query = candidate_query
                            break
            else:
                route_and_search = getattr(
                    self.knowledge_service,
                    "route_and_search",
                    None,
                )

                if callable(route_and_search):
                    routing = None
                    # 自动路由也先使用当前问题；只有短追问无法独立
                    # 确定知识库时，才用历史增强 Query 再路由一次。
                    for route_query in retrieval_queries:
                        candidate_routing = route_and_search(
                            route_query,
                            top_k=self.settings.rag_top_k,
                            similarity_threshold=(
                                self.settings.rag_similarity_threshold
                            ),
                            route_probe_top_k=(
                                self.settings.rag_route_probe_top_k
                            ),
                            route_similarity_threshold=(
                                self.settings
                                .rag_route_similarity_threshold
                            ),
                        )
                        routing = candidate_routing
                        if candidate_routing.knowledge_base_id is not None:
                            break

                    routed_knowledge_base_id = (
                        routing.knowledge_base_id
                        if routing is not None
                        else None
                    )
                    route_score = (
                        routing.route_score
                        if routing is not None
                        else None
                    )

                    if routed_knowledge_base_id is None:
                        route_mode = "none"
                        hits = []
                    else:
                        scoped_search = getattr(
                            self.knowledge_service,
                            "search",
                            None,
                        )
                        if callable(scoped_search):
                            # 第一层：按正常 0.55 阈值，当前问题优先。
                            hits = []
                            for candidate_query in retrieval_queries:
                                candidate_hits = scoped_search(
                                    candidate_query,
                                    knowledge_base_id=(
                                        routed_knowledge_base_id
                                    ),
                                    top_k=self.settings.rag_top_k,
                                    similarity_threshold=(
                                        self.settings
                                        .rag_similarity_threshold
                                    ),
                                )
                                if candidate_hits:
                                    hits = candidate_hits
                                    retrieval_query = candidate_query
                                    break

                            # 第二层：Scoped Retrieval Rescue。
                            # 仍严格限定在 Router 选中的同一个知识库内。
                            rescue_threshold = (
                                self._scoped_rescue_threshold(
                                    normal_threshold=(
                                        self.settings
                                        .rag_similarity_threshold
                                    ),
                                    route_threshold=(
                                        self.settings
                                        .rag_route_similarity_threshold
                                    ),
                                )
                            )
                            if (
                                not hits
                                and rescue_threshold is not None
                                and self._can_attempt_scoped_rescue(
                                    intent=intent,
                                    route_score=route_score,
                                    route_threshold=(
                                        self.settings
                                        .rag_route_similarity_threshold
                                    ),
                                    contextual_followup=(
                                        contextual_followup
                                    ),
                                )
                            ):
                                for candidate_query in retrieval_queries:
                                    candidate_hits = scoped_search(
                                        candidate_query,
                                        knowledge_base_id=(
                                            routed_knowledge_base_id
                                        ),
                                        top_k=self.settings.rag_top_k,
                                        similarity_threshold=(
                                            rescue_threshold
                                        ),
                                    )
                                    if candidate_hits:
                                        hits = candidate_hits
                                        retrieval_query = candidate_query
                                        break
                        elif routing is not None:
                            # 兼容只实现 route_and_search 的旧 FakeKnowledge。
                            hits = list(routing.hits)
                else:
                    # 兼容此前阶段单元测试中的 FakeKnowledge。
                    hits = []
                    for candidate_query in retrieval_queries:
                        candidate_hits = self.knowledge_service.search_any(
                            candidate_query,
                            top_k=self.settings.rag_top_k,
                            similarity_threshold=(
                                self.settings.rag_similarity_threshold
                            ),
                        )
                        if candidate_hits:
                            hits = candidate_hits
                            retrieval_query = candidate_query
                            break
                    routed_knowledge_base_id = (
                        hits[0].knowledge_base_id
                        if hits
                        else None
                    )
                    if routed_knowledge_base_id is None:
                        route_mode = "none"
        except Exception:
            return ChatStreamPlan(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                intent=intent,
                daily_question_count=daily_count,
                retrieval_query=retrieval_query,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
                route_mode=route_mode,
                route_score=route_score,
                hits=(),
                prompt=None,
                fallback_status="failed",
            )

        if not hits:
            return ChatStreamPlan(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                intent=intent,
                daily_question_count=daily_count,
                retrieval_query=retrieval_query,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
                route_mode=route_mode,
                route_score=route_score,
                hits=(),
                prompt=None,
                fallback_status="empty",
            )

        prompt = self.prompt_builder.build(
            question=normalized,
            history=[
                PromptHistoryItem(
                    role=item.role,
                    content=item.content,
                )
                for item in history
            ],
            hits=hits,
        )

        return ChatStreamPlan(
            session_id=session_id,
            user_id=user_id,
            user_message=user_message,
            intent=intent,
            daily_question_count=daily_count,
            retrieval_query=retrieval_query,
            routed_knowledge_base_id=(
                routed_knowledge_base_id
            ),
            route_mode=route_mode,
            route_score=route_score,
            hits=tuple(hits),
            prompt=prompt,
            fallback_status=None,
        )

    def iter_sse(
        self,
        plan: ChatStreamPlan,
    ) -> Iterator[str]:
        yield self._sse(
            "meta",
            {
                "session_id": plan.session_id,
                "user_message_id": plan.user_message.id,
                "intent": plan.intent,
                "daily_question_count": (
                    plan.daily_question_count
                ),
                "retrieval_status": (
                    plan.fallback_status or "matched"
                ),
                "routed_knowledge_base_id": (
                    plan.routed_knowledge_base_id
                ),
                "route_mode": plan.route_mode,
                "route_score": plan.route_score,
            },
        )

        if plan.fallback_status is not None:
            yield from self._fallback_events(
                plan=plan,
                retrieval_status=plan.fallback_status,
            )
            return

        if plan.prompt is None:
            yield from self._fallback_events(
                plan=plan,
                retrieval_status="failed",
            )
            return

        parts: list[str] = []
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        emitted_text = False

        try:
            for chunk in self.chat_model.stream(
                plan.prompt.messages,
                temperature=0.1,
            ):
                if chunk.content:
                    emitted_text = True
                    parts.append(chunk.content)
                    yield self._sse(
                        "delta",
                        {
                            "content": chunk.content,
                        },
                    )

                if chunk.done:
                    prompt_tokens = (
                        chunk.prompt_token_count
                    )
                    completion_tokens = (
                        chunk.completion_token_count
                    )
        except ChatGenerationError as exc:
            # 若已经向浏览器发过部分 token，使用 replace 事件要求前端
            # 丢弃不完整回答并替换为安全兜底文本。
            yield self._sse(
                "error",
                {
                    "code": "llm_stream_failed",
                    "message": "AI 生成中断，已切换安全兜底回答",
                },
            )
            yield from self._fallback_events(
                plan=plan,
                retrieval_status="failed",
                replace=emitted_text,
            )
            return

        raw_answer = "".join(parts)
        normalized = (
            ChatAnswerService._normalize_model_answer(
                self._as_generation_result(
                    content=raw_answer,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            )
        )

        if normalized is None:
            yield from self._fallback_events(
                plan=plan,
                retrieval_status="empty",
                replace=emitted_text,
            )
            return

        normalized = (
            ChatAnswerService._sanitize_source_citations(
                normalized,
                valid_ranks=[
                    source.rank
                    for source in plan.prompt.sources
                ],
            )
        )

        guarded = self._enforce_evidence_guard(
            prompt=plan.prompt,
            answer_text=normalized,
        )
        if guarded is None:
            yield self._sse(
                "error",
                {
                    "code": "evidence_guard_failed",
                    "message": (
                        "AI 回答遗漏关键业务规则，"
                        "已切换安全兜底回答"
                    ),
                },
            )
            yield from self._fallback_events(
                plan=plan,
                retrieval_status="failed",
                replace=emitted_text,
            )
            return

        normalized, repaired_result = guarded
        if repaired_result is not None:
            prompt_tokens = (
                repaired_result.prompt_token_count
            )
            completion_tokens = (
                repaired_result.completion_token_count
            )

        # 模型可能流出了 “[来源 1]”、不存在的 “[来源2]” 等，
        # 最终持久化只允许真实 prompt.sources 中存在的引用编号。
        # 如果标准化后的文本与浏览器当前文本不同，要求前端用 replace
        # 覆盖一次，保证页面、MySQL、历史记录三者一致。
        if normalized != raw_answer.strip():
            yield self._sse(
                "replace",
                {
                    "content": normalized,
                },
            )

        routed_kb = plan.routed_knowledge_base_id
        suggestions = self._suggestions(plan.intent)

        assistant = (
            self.session_service.add_assistant_message(
                session_id=plan.session_id,
                user_id=plan.user_id,
                content=normalized,
                reply_to_message_id=(
                    plan.user_message.id
                ),
                intent=plan.intent,
                routed_knowledge_base_id=routed_kb,
                retrieval_status="matched",
                is_fallback=False,
                prompt_token_estimate=(
                    prompt_tokens
                    if prompt_tokens is not None
                    else ChatAnswerService._estimate_prompt_tokens(
                        plan.prompt.messages
                    )
                ),
                completion_token_count=completion_tokens,
                follow_up_suggestions=suggestions,
                stream_completed=True,
            )
        )

        saved_sources = self._save_sources(
            plan=plan,
            assistant=assistant,
        )

        yield self._sse(
            "sources",
            {
                "items": [
                    self._source_json(item)
                    for item in saved_sources
                ]
            },
        )

        yield self._sse(
            "done",
            {
                "assistant_message_id": assistant.id,
                "content": normalized,
                "is_fallback": False,
                "retrieval_status": "matched",
                "follow_up_suggestions": suggestions,
                "source_count": len(saved_sources),
                "routed_knowledge_base_id": routed_kb,
                "route_mode": plan.route_mode,
                "route_score": plan.route_score,
            },
        )

    def _enforce_evidence_guard(
        self,
        *,
        prompt: BuiltRAGPrompt,
        answer_text: str,
    ) -> tuple[str, ChatGenerationResult | None] | None:
        if not self.settings.rag_answer_guard_enabled:
            return answer_text, None

        validation = self.answer_guard.validate(
            answer_text,
            required_source_ranks=(
                prompt.required_source_ranks
            ),
        )
        if validation.valid:
            return answer_text, None

        current_text = answer_text
        last_result: ChatGenerationResult | None = None

        for _ in range(
            self.settings.rag_answer_repair_attempts
        ):
            repair_messages = (
                self.answer_guard.build_repair_messages(
                    original_messages=prompt.messages,
                    draft=current_text,
                    missing_required_ranks=(
                        validation.missing_required_ranks
                    ),
                )
            )
            try:
                repaired = self.chat_model.generate(
                    repair_messages,
                    temperature=0.0,
                )
            except ChatGenerationError:
                return None

            repaired_text = (
                ChatAnswerService._normalize_model_answer(
                    repaired
                )
            )
            if repaired_text is None:
                return None

            repaired_text = (
                ChatAnswerService._sanitize_source_citations(
                    repaired_text,
                    valid_ranks=[
                        source.rank
                        for source in prompt.sources
                    ],
                )
            )
            validation = self.answer_guard.validate(
                repaired_text,
                required_source_ranks=(
                    prompt.required_source_ranks
                ),
            )
            current_text = repaired_text
            last_result = repaired
            if validation.valid:
                return current_text, last_result

        return None

    def _consume_daily_quota(
        self,
        *,
        user_id: int,
    ) -> int:
        repository = self.session_service.repository

        try:
            count = repository.try_consume_daily_question(
                user_id=user_id,
                daily_limit=(
                    self.settings.daily_question_limit
                ),
            )
            if count is None:
                repository.rollback()
                raise DailyQuestionLimitError(
                    "今日提问次数已达到上限："
                    f"{self.settings.daily_question_limit}"
                )

            repository.commit()
            return count
        except DailyQuestionLimitError:
            raise
        except Exception:
            repository.rollback()
            raise

    def _fallback_events(
        self,
        *,
        plan: ChatStreamPlan,
        retrieval_status: str,
        replace: bool = False,
    ) -> Iterator[str]:
        reply = self.settings.empty_retrieval_reply
        suggestions = self._suggestions(plan.intent)
        routed_kb = plan.routed_knowledge_base_id

        assistant = (
            self.session_service.add_assistant_message(
                session_id=plan.session_id,
                user_id=plan.user_id,
                content=reply,
                reply_to_message_id=(
                    plan.user_message.id
                ),
                intent=plan.intent,
                routed_knowledge_base_id=routed_kb,
                retrieval_status=retrieval_status,
                is_fallback=True,
                follow_up_suggestions=suggestions,
                stream_completed=True,
            )
        )

        yield self._sse(
            "replace" if replace else "delta",
            {
                "content": reply,
            },
        )
        yield self._sse(
            "sources",
            {"items": []},
        )
        yield self._sse(
            "done",
            {
                "assistant_message_id": assistant.id,
                "content": reply,
                "is_fallback": True,
                "retrieval_status": retrieval_status,
                "follow_up_suggestions": suggestions,
                "source_count": 0,
                "routed_knowledge_base_id": routed_kb,
                "route_mode": plan.route_mode,
                "route_score": plan.route_score,
            },
        )

    def _save_sources(
        self,
        *,
        plan: ChatStreamPlan,
        assistant: ChatMessageRecord,
    ) -> tuple[MessageSourceRecord, ...]:
        if plan.prompt is None:
            return ()

        saved = self.session_service.add_message_sources(
            message_id=assistant.id,
            user_id=plan.user_id,
            sources=[
                MessageSourceInput(
                    document_id=item.document_id,
                    chunk_id=item.chunk_id,
                    document_name=item.document_name,
                    chunk_summary=item.content,
                    distance=item.distance,
                    similarity_score=item.similarity,
                    rank=item.rank,
                )
                for item in plan.prompt.sources
            ],
        )
        return tuple(saved)

    def _suggestions(
        self,
        intent: str,
    ) -> list[str]:
        values = ChatAnswerService.FOLLOW_UPS.get(
            intent,
            ChatAnswerService.FOLLOW_UPS["general"],
        )
        return list(
            values[
                : self.settings.follow_up_suggestion_count
            ]
        )

    @staticmethod
    def _sse(
        event: str,
        data: dict,
    ) -> str:
        return (
            f"event: {event}\n"
            "data: "
            f"{json.dumps(data, ensure_ascii=False)}\n\n"
        )

    @staticmethod
    def _source_json(
        item: MessageSourceRecord,
    ) -> dict:
        return {
            "id": item.id,
            "message_id": item.message_id,
            "document_id": item.document_id,
            "chunk_id": item.chunk_id,
            "document_name": item.document_name,
            "chunk_summary": item.chunk_summary,
            "distance": item.distance,
            "similarity_score": item.similarity_score,
            "rank": item.rank,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _as_generation_result(
        *,
        content: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ):
        from app.services.llm.chat_service import (
            ChatGenerationResult,
        )

        return ChatGenerationResult(
            content=content,
            model="stream",
            prompt_token_count=prompt_tokens,
            completion_token_count=completion_tokens,
            total_duration_ns=None,
            load_duration_ns=None,
        )
