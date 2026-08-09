from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Sequence

from app.core.config import get_settings
from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatRepository,
    ChatSessionRecord,
    MessageFeedbackRecord,
    MessageSourceRecord,
)


class ChatServiceError(RuntimeError):
    """会话业务错误。"""


class ChatSessionNotFoundError(ChatServiceError):
    """会话不存在或不属于当前用户。"""


class ChatMessageNotFoundError(ChatServiceError):
    """消息不存在或不属于当前用户。"""


class ChatValidationError(ChatServiceError):
    """会话或消息参数不合法。"""


@dataclass(frozen=True)
class ContextMessage:
    role: str
    content: str


@dataclass(frozen=True)
class MessageSourceInput:
    document_name: str
    chunk_summary: str
    rank: int
    document_id: int | None = None
    chunk_id: int | None = None
    distance: float | None = None
    similarity_score: float | None = None


class ChatSessionService:
    """会话与消息基础业务层。"""

    SESSION_STATUSES = {"active", "archived"}
    MESSAGE_ROLES = {"user", "assistant", "system"}
    RETRIEVAL_STATUSES = {
        "matched",
        "empty",
        "skipped",
        "failed",
    }

    def __init__(
        self,
        repository: ChatRepository,
    ) -> None:
        self.repository = repository
        settings = get_settings()
        self.question_max_length = (
            settings.question_max_length
        )
        self.context_history_rounds = (
            settings.context_history_rounds
        )

    def create_session(
        self,
        *,
        user_id: int,
        title: str = "新会话",
        selected_knowledge_base_id: int | None = None,
    ) -> ChatSessionRecord:
        normalized_title = self._normalize_title(title)

        try:
            session = self.repository.create_session(
                user_id=user_id,
                title=normalized_title,
                selected_knowledge_base_id=(
                    selected_knowledge_base_id
                ),
            )
            self.repository.commit()
            return session
        except LookupError as exc:
            self.repository.rollback()
            raise ChatValidationError(str(exc)) from exc
        except Exception:
            self.repository.rollback()
            raise

    def get_session(
        self,
        *,
        session_id: int,
        user_id: int,
        include_archived: bool = True,
    ) -> ChatSessionRecord:
        session = self.repository.get_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=include_archived,
        )
        if session is None:
            raise ChatSessionNotFoundError(
                "会话不存在或无权访问"
            )
        return session

    def list_sessions(
        self,
        *,
        user_id: int,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSessionRecord]:
        if status is not None:
            self._validate_session_status(status)
        if not 1 <= limit <= 200:
            raise ChatValidationError(
                "limit 必须在 1 到 200 之间"
            )
        if offset < 0:
            raise ChatValidationError(
                "offset 不能小于 0"
            )

        return self.repository.list_sessions(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def count_sessions(
        self,
        *,
        user_id: int,
        status: str | None = None,
    ) -> int:
        if status is not None:
            self._validate_session_status(status)
        return self.repository.count_sessions(
            user_id=user_id,
            status=status,
        )

    def rename_session(
        self,
        *,
        session_id: int,
        user_id: int,
        title: str,
    ) -> ChatSessionRecord:
        self.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )
        normalized_title = self._normalize_title(title)

        try:
            session = self.repository.update_session_title(
                session_id=session_id,
                user_id=user_id,
                title=normalized_title,
            )
            self.repository.commit()
            return session
        except LookupError as exc:
            self.repository.rollback()
            raise ChatSessionNotFoundError(
                str(exc)
            ) from exc
        except Exception:
            self.repository.rollback()
            raise

    def select_knowledge_base(
        self,
        *,
        session_id: int,
        user_id: int,
        knowledge_base_id: int | None,
    ) -> ChatSessionRecord:
        self.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )

        try:
            session = (
                self.repository.update_selected_knowledge_base(
                    session_id=session_id,
                    user_id=user_id,
                    knowledge_base_id=knowledge_base_id,
                )
            )
            self.repository.commit()
            return session
        except LookupError as exc:
            self.repository.rollback()
            raise ChatValidationError(str(exc)) from exc
        except Exception:
            self.repository.rollback()
            raise

    def archive_session(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> ChatSessionRecord:
        self.get_session(
            session_id=session_id,
            user_id=user_id,
        )

        try:
            session = self.repository.archive_session(
                session_id=session_id,
                user_id=user_id,
            )
            self.repository.commit()
            return session
        except LookupError as exc:
            self.repository.rollback()
            raise ChatSessionNotFoundError(
                str(exc)
            ) from exc
        except Exception:
            self.repository.rollback()
            raise

    def restore_session(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> ChatSessionRecord:
        self.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=True,
        )

        try:
            session = self.repository.restore_session(
                session_id=session_id,
                user_id=user_id,
            )
            self.repository.commit()
            return session
        except LookupError as exc:
            self.repository.rollback()
            raise ChatSessionNotFoundError(
                str(exc)
            ) from exc
        except Exception:
            self.repository.rollback()
            raise

    def add_user_message(
        self,
        *,
        session_id: int,
        user_id: int,
        content: str,
        intent: str | None = None,
    ) -> ChatMessageRecord:
        session = self.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )

        normalized_content = self._normalize_content(content)
        if len(normalized_content) > self.question_max_length:
            raise ChatValidationError(
                "单次提问不能超过 "
                f"{self.question_max_length} 字"
            )

        try:
            if session.title == "新会话":
                self.repository.update_session_title(
                    session_id=session_id,
                    user_id=user_id,
                    title=self._derive_title(
                        normalized_content
                    ),
                )

            message = self.repository.add_message(
                session_id=session_id,
                role="user",
                content=normalized_content,
                user_id=user_id,
                intent=self._normalize_optional_short_text(
                    intent,
                    field_name="intent",
                    max_length=50,
                ),
                question_char_count=len(
                    normalized_content
                ),
            )
            self.repository.commit()
            return message
        except LookupError as exc:
            self.repository.rollback()
            raise ChatValidationError(str(exc)) from exc
        except Exception:
            self.repository.rollback()
            raise

    def add_assistant_message(
        self,
        *,
        session_id: int,
        user_id: int,
        content: str,
        reply_to_message_id: int | None = None,
        intent: str | None = None,
        routed_knowledge_base_id: int | None = None,
        retrieval_status: str | None = None,
        is_fallback: bool = False,
        prompt_token_estimate: int | None = None,
        completion_token_count: int | None = None,
        follow_up_suggestions: Sequence[str] | None = None,
        stream_completed: bool = True,
    ) -> ChatMessageRecord:
        self.get_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )
        normalized_content = self._normalize_content(content)

        if retrieval_status is not None:
            self._validate_retrieval_status(
                retrieval_status
            )

        suggestions = self._normalize_suggestions(
            follow_up_suggestions
        )

        for field_name, value in (
            (
                "prompt_token_estimate",
                prompt_token_estimate,
            ),
            (
                "completion_token_count",
                completion_token_count,
            ),
        ):
            if value is not None and value < 0:
                raise ChatValidationError(
                    f"{field_name} 不能小于 0"
                )

        try:
            if reply_to_message_id is not None:
                reply_message = self.repository.get_message(
                    reply_to_message_id
                )
                if (
                    reply_message is None
                    or reply_message.session_id
                    != session_id
                    or reply_message.role != "user"
                ):
                    raise ChatValidationError(
                        "reply_to_message_id "
                        "必须指向当前会话的用户消息"
                    )

            message = self.repository.add_message(
                session_id=session_id,
                role="assistant",
                content=normalized_content,
                user_id=None,
                reply_to_message_id=reply_to_message_id,
                intent=self._normalize_optional_short_text(
                    intent,
                    field_name="intent",
                    max_length=50,
                ),
                routed_knowledge_base_id=(
                    routed_knowledge_base_id
                ),
                retrieval_status=retrieval_status,
                is_fallback=is_fallback,
                prompt_token_estimate=(
                    prompt_token_estimate
                ),
                completion_token_count=(
                    completion_token_count
                ),
                follow_up_suggestions=suggestions,
                stream_completed_at=(
                    datetime.now(UTC).replace(
                        tzinfo=None
                    )
                    if stream_completed
                    else None
                ),
            )
            self.repository.commit()
            return message
        except ChatServiceError:
            self.repository.rollback()
            raise
        except LookupError as exc:
            self.repository.rollback()
            raise ChatValidationError(str(exc)) from exc
        except Exception:
            self.repository.rollback()
            raise

    def list_messages(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> list[ChatMessageRecord]:
        try:
            return self.repository.list_messages_owned(
                session_id=session_id,
                user_id=user_id,
            )
        except LookupError as exc:
            raise ChatSessionNotFoundError(
                str(exc)
            ) from exc

    def recent_context(
        self,
        *,
        session_id: int,
        user_id: int,
        rounds: int | None = None,
    ) -> list[ContextMessage]:
        selected_rounds = (
            self.context_history_rounds
            if rounds is None
            else rounds
        )
        if not 1 <= selected_rounds <= 50:
            raise ChatValidationError(
                "上下文轮数必须在 1 到 50 之间"
            )

        try:
            messages = (
                self.repository.list_recent_messages_owned(
                    session_id=session_id,
                    user_id=user_id,
                    max_messages=selected_rounds * 2,
                )
            )
        except LookupError as exc:
            raise ChatSessionNotFoundError(
                str(exc)
            ) from exc

        return [
            ContextMessage(
                role=message.role,
                content=message.content,
            )
            for message in messages
        ]

    def add_message_sources(
        self,
        *,
        message_id: int,
        user_id: int,
        sources: Sequence[MessageSourceInput],
    ) -> list[MessageSourceRecord]:
        if not sources:
            return []

        message = self.repository.get_message(message_id)
        if message is None:
            raise ChatValidationError("消息不存在")

        self.get_session(
            session_id=message.session_id,
            user_id=user_id,
        )

        if message.role != "assistant":
            raise ChatValidationError(
                "知识来源只能关联 assistant 消息"
            )

        ranks = [source.rank for source in sources]
        if any(rank <= 0 for rank in ranks):
            raise ChatValidationError(
                "来源 rank 必须从 1 开始"
            )
        if len(set(ranks)) != len(ranks):
            raise ChatValidationError(
                "同一消息的来源 rank 不能重复"
            )

        created: list[MessageSourceRecord] = []
        try:
            for source in sorted(
                sources,
                key=lambda item: item.rank,
            ):
                document_name = source.document_name.strip()
                summary = source.chunk_summary.strip()

                if not document_name:
                    raise ChatValidationError(
                        "来源 document_name 不能为空"
                    )
                if len(document_name) > 255:
                    raise ChatValidationError(
                        "来源 document_name "
                        "不能超过 255 个字符"
                    )
                if not summary:
                    raise ChatValidationError(
                        "来源 chunk_summary 不能为空"
                    )

                created.append(
                    self.repository.add_message_source(
                        message_id=message_id,
                        document_id=source.document_id,
                        chunk_id=source.chunk_id,
                        document_name=document_name,
                        chunk_summary=summary,
                        distance=source.distance,
                        similarity_score=(
                            source.similarity_score
                        ),
                        rank=source.rank,
                    )
                )

            self.repository.commit()
            return created
        except ChatServiceError:
            self.repository.rollback()
            raise
        except Exception:
            self.repository.rollback()
            raise

    def list_message_sources(
        self,
        *,
        message_id: int,
        user_id: int,
    ) -> list[MessageSourceRecord]:
        return self.repository.list_message_sources_owned(
            message_id=message_id,
            user_id=user_id,
        )

    def submit_message_feedback(
        self,
        *,
        message_id: int,
        user_id: int,
        rating: int,
        comment: str | None = None,
    ) -> MessageFeedbackRecord:
        if rating not in {-1, 1}:
            raise ChatValidationError(
                "rating 只能是 1（点赞）或 -1（点踩）"
            )

        self._require_owned_assistant_message(
            message_id=message_id,
            user_id=user_id,
        )
        normalized_comment = (
            self._normalize_feedback_comment(comment)
        )

        try:
            feedback = self.repository.upsert_message_feedback(
                message_id=message_id,
                user_id=user_id,
                rating=rating,
                comment=normalized_comment,
            )
            self.repository.commit()
            return feedback
        except LookupError as exc:
            self.repository.rollback()
            raise ChatValidationError(str(exc)) from exc
        except Exception:
            self.repository.rollback()
            raise

    def list_session_feedback(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> list[MessageFeedbackRecord]:
        self.get_session(
            session_id=session_id,
            user_id=user_id,
        )
        try:
            return self.repository.list_session_feedback_owned(
                session_id=session_id,
                user_id=user_id,
            )
        except LookupError as exc:
            raise ChatSessionNotFoundError(
                "会话不存在或无权访问"
            ) from exc

    def delete_message_feedback(
        self,
        *,
        message_id: int,
        user_id: int,
    ) -> bool:
        self._require_owned_assistant_message(
            message_id=message_id,
            user_id=user_id,
        )

        try:
            deleted = self.repository.delete_message_feedback(
                message_id=message_id,
                user_id=user_id,
            )
            self.repository.commit()
            return deleted
        except Exception:
            self.repository.rollback()
            raise

    def _require_owned_assistant_message(
        self,
        *,
        message_id: int,
        user_id: int,
    ) -> ChatMessageRecord:
        message = self.repository.get_message(message_id)
        if message is None:
            raise ChatMessageNotFoundError(
                "消息不存在或无权访问"
            )

        try:
            self.get_session(
                session_id=message.session_id,
                user_id=user_id,
            )
        except ChatSessionNotFoundError as exc:
            raise ChatMessageNotFoundError(
                "消息不存在或无权访问"
            ) from exc

        if message.role != "assistant":
            raise ChatValidationError(
                "只能对 AI assistant 回答提交反馈"
            )
        return message

    @staticmethod
    def _normalize_feedback_comment(
        comment: str | None,
    ) -> str | None:
        if comment is None:
            return None
        normalized = comment.strip()
        if not normalized:
            return None
        if len(normalized) > 1000:
            raise ChatValidationError(
                "文字反馈不能超过 1000 个字符"
            )
        return normalized

    @classmethod
    def _validate_session_status(
        cls,
        status: str,
    ) -> None:
        if status not in cls.SESSION_STATUSES:
            raise ChatValidationError(
                "status 只能是 active 或 archived"
            )

    @classmethod
    def _validate_retrieval_status(
        cls,
        retrieval_status: str,
    ) -> None:
        if (
            retrieval_status
            not in cls.RETRIEVAL_STATUSES
        ):
            raise ChatValidationError(
                "retrieval_status 必须是 "
                "matched / empty / skipped / failed"
            )

    @staticmethod
    def _normalize_title(title: str) -> str:
        normalized = re.sub(
            r"\s+",
            " ",
            title,
        ).strip()
        if not normalized:
            raise ChatValidationError(
                "会话标题不能为空"
            )
        if len(normalized) > 255:
            raise ChatValidationError(
                "会话标题不能超过 255 个字符"
            )
        return normalized

    @staticmethod
    def _normalize_content(content: str) -> str:
        normalized = content.strip()
        if not normalized:
            raise ChatValidationError(
                "消息内容不能为空"
            )
        return normalized

    @staticmethod
    def _derive_title(content: str) -> str:
        single_line = re.sub(
            r"\s+",
            " ",
            content,
        ).strip()
        if len(single_line) <= 30:
            return single_line
        return single_line[:30].rstrip() + "…"

    @staticmethod
    def _normalize_optional_short_text(
        value: str | None,
        *,
        field_name: str,
        max_length: int,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > max_length:
            raise ChatValidationError(
                f"{field_name} 不能超过 "
                f"{max_length} 个字符"
            )
        return normalized

    @staticmethod
    def _normalize_suggestions(
        values: Sequence[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None

        normalized = [
            item.strip()
            for item in values
            if item.strip()
        ]
        if len(normalized) > 10:
            raise ChatValidationError(
                "追问建议最多 10 条"
            )
        if any(
            len(item) > 200
            for item in normalized
        ):
            raise ChatValidationError(
                "单条追问建议不能超过 200 个字符"
            )
        return normalized
