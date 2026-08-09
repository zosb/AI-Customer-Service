from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from app.core.config import get_settings
from app.repositories.chat_repository import (
    ChatMessageRecord,
    MessageSourceRecord,
)
from app.services.chat.prompt_builder import (
    BuiltRAGPrompt,
    NO_RELIABLE_ANSWER_SENTINEL,
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
    OllamaChatService,
)
from app.services.rag.answer_guard import (
    AnswerEvidenceGuard,
)


class ChatAnswerError(RuntimeError):
    """AI 客服问答核心链路错误。"""


class DailyQuestionLimitError(ChatAnswerError):
    """用户达到当日提问次数上限。"""


@dataclass(frozen=True)
class ChatAnswerResult:
    user_message: ChatMessageRecord
    assistant_message: ChatMessageRecord
    sources: tuple[MessageSourceRecord, ...]
    retrieval_hits: tuple[KnowledgeSearchHit, ...]
    daily_question_count: int
    retrieval_query: str


class ChatAnswerService:
    """
    非流式 RAG 问答核心编排。

    流程：
    额度检查
    -> 读取最近 N 轮历史
    -> 保存 user message
    -> qwen3-embedding
    -> 多知识库自动路由（未手动绑定时）
    -> 获胜知识库内 Chroma Top-K
    -> MySQL 二次过滤有效 Chunk/Document/KnowledgeBase
    -> 相似度阈值
    -> 防幻觉 Prompt
    -> qwen3.5 Chat
    -> assistant message
    -> message_sources
    -> follow-up suggestions。
    """

    INTENT_PATTERNS: tuple[
        tuple[str, tuple[str, ...]],
        ...
    ] = (
        (
            "refund",
            (
                "退款",
                "退钱",
                "到账",
                "原路退回",
            ),
        ),
        (
            "return_exchange",
            (
                "退货",
                "换货",
                "退换",
                "七天无理由",
                "质量问题",
            ),
        ),
        (
            "logistics",
            (
                "物流",
                "快递",
                "发货",
                "配送",
                "签收",
                "运费",
            ),
        ),
        (
            "product",
            (
                "产品",
                "功能",
                "规格",
                "型号",
                "价格",
                "套餐",
            ),
        ),
        (
            "account",
            (
                "账号",
                "登录",
                "注册",
                "密码",
                "手机号",
                "邮箱",
            ),
        ),
        (
            "human_service",
            (
                "人工客服",
                "人工",
                "客服时间",
                "工作时间",
            ),
        ),
    )

    FOLLOW_UPS: dict[str, tuple[str, ...]] = {
        "refund": (
            "如何查询退款进度？",
            "超过预计时间还没到账怎么办？",
            "退款会原路退回吗？",
        ),
        "return_exchange": (
            "退换货需要满足哪些条件？",
            "退货运费由谁承担？",
            "如何提交退换货申请？",
        ),
        "logistics": (
            "如何查询物流进度？",
            "一直没有发货怎么办？",
            "签收异常应该如何处理？",
        ),
        "product": (
            "这个产品适合哪些场景？",
            "还有哪些相关功能？",
            "如何进一步了解产品信息？",
        ),
        "account": (
            "忘记密码应该怎么办？",
            "手机号无法登录怎么办？",
            "如何确认账号状态？",
        ),
        "human_service": (
            "人工客服的服务时间是什么？",
            "如何联系人工客服？",
            "非工作时间可以留言吗？",
        ),
        "general": (
            "还有哪些相关信息？",
            "这个问题需要人工客服确认吗？",
            "可以换一种方式说明吗？",
        ),
    }

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

    def answer(
        self,
        *,
        session_id: int,
        user_id: int,
        question: str,
    ) -> ChatAnswerResult:
        normalized_question = question.strip()
        if not normalized_question:
            raise ChatValidationError(
                "消息内容不能为空"
            )
        if (
            len(normalized_question)
            > self.settings.question_max_length
        ):
            raise ChatValidationError(
                "单次提问不能超过 "
                f"{self.settings.question_max_length} 字"
            )

        session = self.session_service.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )

        # 必须在写入当前问题前读取历史，否则当前问题会在 Prompt 中重复。
        history = self.session_service.recent_context(
            session_id=session_id,
            user_id=user_id,
            rounds=self.settings.context_history_rounds,
        )

        daily_count = self._consume_daily_quota(
            user_id=user_id
        )
        intent = self.classify_intent(
            normalized_question
        )

        user_message = (
            self.session_service.add_user_message(
                session_id=session_id,
                user_id=user_id,
                content=normalized_question,
                intent=intent,
            )
        )

        retrieval_queries = self._build_retrieval_queries(
            question=normalized_question,
            history=history,
        )
        # 记录真正用于最终 Chunk 检索的 Query，便于审计与测试。
        retrieval_query = retrieval_queries[0]

        routed_knowledge_base_id = (
            session.selected_knowledge_base_id
        )

        try:
            if routed_knowledge_base_id is not None:
                # 用户显式绑定知识库时保持人工选择优先。
                # 先用“当前问题本身”检索，避免把上一轮无关问题拼进去后
                # 稀释 embedding；只有当前问题没有命中时才回退到
                # 带对话上下文的检索 Query。
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
            else:
                # 未绑定知识库：先用当前问题做自动路由；如果它是
                # “那这个呢？”一类真正依赖历史的追问，当前问题无法
                # 独立路由时，再回退到上下文增强 Query。
                route_and_search = getattr(
                    self.knowledge_service,
                    "route_and_search",
                    None,
                )
                if callable(route_and_search):
                    routing = None
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
                    hits = []
                    if routed_knowledge_base_id is not None:
                        scoped_search = getattr(
                            self.knowledge_service,
                            "search",
                            None,
                        )
                        if callable(scoped_search):
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
                        elif routing is not None:
                            # 兼容仅实现 route_and_search 的轻量 Fake。
                            hits = list(routing.hits)
                else:
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
        except Exception:
            return self._save_fallback(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                intent=intent,
                retrieval_status="failed",
                daily_count=daily_count,
                hits=[],
                retrieval_query=retrieval_query,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
            )

        if not hits:
            return self._save_fallback(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                intent=intent,
                retrieval_status="empty",
                daily_count=daily_count,
                hits=[],
                retrieval_query=retrieval_query,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
            )

        prompt_history = [
            PromptHistoryItem(
                role=item.role,
                content=item.content,
            )
            for item in history
        ]

        prompt = self.prompt_builder.build(
            question=normalized_question,
            history=prompt_history,
            hits=hits,
        )

        try:
            model_result = self.chat_model.generate(
                prompt.messages,
                temperature=0.1,
            )
        except ChatGenerationError:
            return self._save_fallback(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                intent=intent,
                retrieval_status="failed",
                daily_count=daily_count,
                hits=hits,
                retrieval_query=retrieval_query,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
            )

        answer_text = self._normalize_model_answer(
            model_result
        )

        if answer_text is not None:
            answer_text = self._sanitize_source_citations(
                answer_text,
                valid_ranks=[
                    source.rank
                    for source in prompt.sources
                ],
            )

        if answer_text is None:
            return self._save_fallback(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                intent=intent,
                retrieval_status="empty",
                daily_count=daily_count,
                hits=hits,
                retrieval_query=retrieval_query,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
            )

        guarded = self._enforce_evidence_guard(
            prompt=prompt,
            answer_text=answer_text,
            model_result=model_result,
        )
        if guarded is None:
            return self._save_fallback(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                intent=intent,
                retrieval_status="failed",
                daily_count=daily_count,
                hits=hits,
                retrieval_query=retrieval_query,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
            )
        answer_text, model_result = guarded

        assistant_message = (
            self.session_service.add_assistant_message(
                session_id=session_id,
                user_id=user_id,
                content=answer_text,
                reply_to_message_id=user_message.id,
                intent=intent,
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
                retrieval_status="matched",
                is_fallback=False,
                prompt_token_estimate=(
                    model_result.prompt_token_count
                    if model_result.prompt_token_count
                    is not None
                    else self._estimate_prompt_tokens(
                        prompt.messages
                    )
                ),
                completion_token_count=(
                    model_result.completion_token_count
                ),
                follow_up_suggestions=(
                    self._suggestions(intent)
                ),
                stream_completed=True,
            )
        )

        source_inputs = [
            MessageSourceInput(
                document_id=source.document_id,
                chunk_id=source.chunk_id,
                document_name=source.document_name,
                chunk_summary=source.content,
                distance=source.distance,
                similarity_score=source.similarity,
                rank=source.rank,
            )
            for source in prompt.sources
        ]

        saved_sources = (
            self.session_service.add_message_sources(
                message_id=assistant_message.id,
                user_id=user_id,
                sources=source_inputs,
            )
        )

        return ChatAnswerResult(
            user_message=user_message,
            assistant_message=assistant_message,
            sources=tuple(saved_sources),
            retrieval_hits=tuple(hits),
            daily_question_count=daily_count,
            retrieval_query=retrieval_query,
        )

    def _enforce_evidence_guard(
        self,
        *,
        prompt: BuiltRAGPrompt,
        answer_text: str,
        model_result: ChatGenerationResult,
    ) -> tuple[str, ChatGenerationResult] | None:
        if not self.settings.rag_answer_guard_enabled:
            return answer_text, model_result

        validation = self.answer_guard.validate(
            answer_text,
            required_source_ranks=(
                prompt.required_source_ranks
            ),
        )
        if validation.valid:
            return answer_text, model_result

        current_text = answer_text
        current_result = model_result

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
                repaired_result = self.chat_model.generate(
                    repair_messages,
                    temperature=0.0,
                )
            except ChatGenerationError:
                return None

            repaired_text = self._normalize_model_answer(
                repaired_result
            )
            if repaired_text is None:
                return None

            repaired_text = self._sanitize_source_citations(
                repaired_text,
                valid_ranks=[
                    source.rank
                    for source in prompt.sources
                ],
            )
            validation = self.answer_guard.validate(
                repaired_text,
                required_source_ranks=(
                    prompt.required_source_ranks
                ),
            )
            current_text = repaired_text
            current_result = repaired_result
            if validation.valid:
                return current_text, current_result

        return None

    def _consume_daily_quota(
        self,
        *,
        user_id: int,
    ) -> int:
        repository = self.session_service.repository

        try:
            count = (
                repository.try_consume_daily_question(
                    user_id=user_id,
                    daily_limit=(
                        self.settings.daily_question_limit
                    ),
                )
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

    def _save_fallback(
        self,
        *,
        session_id: int,
        user_id: int,
        user_message: ChatMessageRecord,
        intent: str,
        retrieval_status: str,
        daily_count: int,
        hits: Sequence[KnowledgeSearchHit],
        retrieval_query: str,
        routed_knowledge_base_id: int | None = None,
    ) -> ChatAnswerResult:
        routed_kb = (
            routed_knowledge_base_id
            if routed_knowledge_base_id is not None
            else (
                hits[0].knowledge_base_id
                if hits
                else None
            )
        )

        assistant = (
            self.session_service.add_assistant_message(
                session_id=session_id,
                user_id=user_id,
                content=(
                    self.settings.empty_retrieval_reply
                ),
                reply_to_message_id=user_message.id,
                intent=intent,
                routed_knowledge_base_id=routed_kb,
                retrieval_status=retrieval_status,
                is_fallback=True,
                follow_up_suggestions=(
                    self._suggestions(intent)
                ),
                stream_completed=True,
            )
        )

        return ChatAnswerResult(
            user_message=user_message,
            assistant_message=assistant,
            sources=(),
            retrieval_hits=tuple(hits),
            daily_question_count=daily_count,
            retrieval_query=retrieval_query,
        )

    @staticmethod
    def _normalize_model_answer(
        result: ChatGenerationResult,
    ) -> str | None:
        content = re.sub(
            r"<think>.*?</think>",
            "",
            result.content,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

        # 统一模型可能产生的来源引用格式：
        # [来源 1] / [ 来源1 ] / 【来源 1】 -> [来源1]
        # 这样数据库、前端和自动化验收只处理一种规范格式。
        content = re.sub(
            r"[\[【]\s*来源\s*(\d+)\s*[\]】]",
            lambda match: f"[来源{match.group(1)}]",
            content,
        )

        if not content:
            return None
        if (
            NO_RELIABLE_ANSWER_SENTINEL
            in content
        ):
            return None
        return content

    @staticmethod
    def _sanitize_source_citations(
        content: str,
        *,
        valid_ranks: Sequence[int],
    ) -> str:
        """
        保证模型正文中的 [来源N] 与真实检索来源严格一致。

        规则：
        1. 没有真实来源时，删除所有来源标记；
        2. 只有一个真实来源时，模型即使幻觉出 [来源2]/[来源3]，
           也统一映射为唯一存在的 [来源1]；
        3. 有多个真实来源时，只保留实际存在的 rank，
           删除超出范围或不存在的来源编号；
        4. 连续重复的同一引用自动去重。
        """
        valid = sorted(
            {
                int(rank)
                for rank in valid_ranks
                if isinstance(rank, int) and rank > 0
            }
        )

        citation_pattern = re.compile(
            r"\[来源(\d+)\]"
        )

        if not valid:
            sanitized = citation_pattern.sub("", content)
        elif len(valid) == 1:
            only = valid[0]
            sanitized = citation_pattern.sub(
                f"[来源{only}]",
                content,
            )
        else:
            valid_set = set(valid)

            def replace_citation(
                match: re.Match[str],
            ) -> str:
                rank = int(match.group(1))
                if rank in valid_set:
                    return f"[来源{rank}]"
                return ""

            sanitized = citation_pattern.sub(
                replace_citation,
                content,
            )

        # 模型可能输出 [来源1][来源1]，统一去重。
        duplicate_pattern = re.compile(
            r"(\[来源(\d+)\])(?:\s*\1)+"
        )
        sanitized = duplicate_pattern.sub(
            r"\1",
            sanitized,
        )

        # 删除无效引用后，避免产生多余双空格。
        sanitized = re.sub(
            r"[ \t]{2,}",
            " ",
            sanitized,
        ).strip()

        return sanitized

    @staticmethod
    def _build_retrieval_query(
        *,
        question: str,
        history: Sequence[object],
    ) -> str:
        """构造“上下文增强”的追问检索 Query。

        这里不再只看紧邻的上一条用户问题。真实对话里经常出现：
        “X1 保修多久？” -> “电话多少？” -> “黑色型号代码？”。
        如果只拼最后一问，“电话多少”会稀释第三问的产品语义。

        因此额外向前寻找最近一条带明显产品/业务标识的“主题锚点”，
        但该增强 Query 只作为第二候选；正式检索永远先尝试当前问题本身。
        Prompt 仍保留完整最近 N 轮历史。
        """
        user_questions: list[str] = []
        for item in history:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
            if (
                role == "user"
                and isinstance(content, str)
                and content.strip()
            ):
                user_questions.append(content.strip())

        if not user_questions:
            return question

        previous_user = user_questions[-1]
        topic_anchor: str | None = None

        # 型号/订单号/产品编码等通常是最稳定的对话主题锚点。
        # 例如 X1、XH-X1-BLK、A12 Pro。
        anchor_pattern = re.compile(
            r"(?i)(?:^|\s|[^A-Za-z0-9])"
            r"[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*"
        )
        for candidate in reversed(user_questions):
            if anchor_pattern.search(candidate):
                topic_anchor = candidate
                break

        parts: list[str] = []
        if topic_anchor and topic_anchor != previous_user:
            parts.append(f"对话主题：{topic_anchor}")
        parts.append(f"上一轮用户问题：{previous_user}")
        parts.append(f"当前追问：{question}")
        return "\n".join(parts)

    @classmethod
    def _build_retrieval_queries(
        cls,
        *,
        question: str,
        history: Sequence[object],
    ) -> tuple[str, ...]:
        """返回按优先级排序的检索 Query。

        第一候选永远是当前问题本身，避免历史语义稀释；
        第二候选才是带主题锚点/上一轮问题的上下文增强 Query，
        用来处理“那这个呢？”等无法独立理解的追问。
        """
        primary = question.strip()
        contextual = cls._build_retrieval_query(
            question=primary,
            history=history,
        ).strip()

        if not contextual or contextual == primary:
            return (primary,)
        return (primary, contextual)

    def _suggestions(
        self,
        intent: str,
    ) -> list[str]:
        values = self.FOLLOW_UPS.get(
            intent,
            self.FOLLOW_UPS["general"],
        )
        return list(
            values[
                : self.settings.follow_up_suggestion_count
            ]
        )

    @classmethod
    def classify_intent(
        cls,
        question: str,
    ) -> str:
        normalized = question.strip().lower()

        for intent, keywords in cls.INTENT_PATTERNS:
            if any(
                keyword.lower() in normalized
                for keyword in keywords
            ):
                return intent

        return "general"

    @staticmethod
    def _estimate_prompt_tokens(
        messages: Sequence[object],
    ) -> int:
        chars = 0
        for item in messages:
            content = getattr(item, "content", "")
            if isinstance(content, str):
                chars += len(content)

        return max(1, (chars + 2) // 3)
