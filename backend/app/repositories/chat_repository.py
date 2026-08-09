from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ChatSessionRecord:
    id: int
    user_id: int
    title: str
    status: str
    selected_knowledge_base_id: int | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ChatMessageRecord:
    id: int
    session_id: int
    user_id: int | None
    reply_to_message_id: int | None
    role: str
    content: str
    intent: str | None
    routed_knowledge_base_id: int | None
    retrieval_status: str | None
    is_fallback: bool
    question_char_count: int | None
    prompt_token_estimate: int | None
    completion_token_count: int | None
    follow_up_suggestions: list[str] | None
    stream_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageSourceRecord:
    id: int
    message_id: int
    document_id: int | None
    chunk_id: int | None
    document_name: str
    chunk_summary: str
    distance: float | None
    similarity_score: float | None
    rank: int
    created_at: datetime


@dataclass(frozen=True)
class MessageFeedbackRecord:
    id: int
    message_id: int
    user_id: int
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime


class ChatRepository:
    """会话/消息 MySQL 仓储。"""

    def __init__(self, database: Session) -> None:
        self.database = database

    def create_session(
        self,
        *,
        user_id: int,
        title: str,
        selected_knowledge_base_id: int | None = None,
    ) -> ChatSessionRecord:
        if selected_knowledge_base_id is not None:
            self.require_active_knowledge_base(
                selected_knowledge_base_id
            )

        result = self.database.execute(
            text(
                """
                INSERT INTO chat_sessions (
                    user_id,
                    title,
                    status,
                    selected_knowledge_base_id
                )
                VALUES (
                    :user_id,
                    :title,
                    'active',
                    :selected_knowledge_base_id
                )
                """
            ),
            {
                "user_id": user_id,
                "title": title,
                "selected_knowledge_base_id":
                    selected_knowledge_base_id,
            },
        )
        session_id = int(result.lastrowid)
        return self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=True,
        )

    def get_owned_session(
        self,
        *,
        session_id: int,
        user_id: int,
        include_archived: bool = True,
    ) -> ChatSessionRecord | None:
        filters = [
            "id = :session_id",
            "user_id = :user_id",
        ]
        if not include_archived:
            filters.append("status = 'active'")

        row = self.database.execute(
            text(
                f"""
                SELECT
                    id,
                    user_id,
                    title,
                    status,
                    selected_knowledge_base_id,
                    last_message_at,
                    created_at,
                    updated_at
                FROM chat_sessions
                WHERE {" AND ".join(filters)}
                LIMIT 1
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
            },
        ).mappings().first()

        return (
            self._session_from_mapping(row)
            if row is not None
            else None
        )

    def require_owned_session(
        self,
        *,
        session_id: int,
        user_id: int,
        include_archived: bool = True,
    ) -> ChatSessionRecord:
        session = self.get_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=include_archived,
        )
        if session is None:
            raise LookupError(
                "会话不存在、无权访问或状态不可用"
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
        filters = ["user_id = :user_id"]
        parameters: dict[str, Any] = {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
        }

        if status is not None:
            filters.append("status = :status")
            parameters["status"] = status

        rows = self.database.execute(
            text(
                f"""
                SELECT
                    id,
                    user_id,
                    title,
                    status,
                    selected_knowledge_base_id,
                    last_message_at,
                    created_at,
                    updated_at
                FROM chat_sessions
                WHERE {" AND ".join(filters)}
                ORDER BY
                    COALESCE(last_message_at, created_at) DESC,
                    id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            parameters,
        ).mappings().all()

        return [
            self._session_from_mapping(row)
            for row in rows
        ]

    def count_sessions(
        self,
        *,
        user_id: int,
        status: str | None = None,
    ) -> int:
        filters = ["user_id = :user_id"]
        parameters: dict[str, Any] = {
            "user_id": user_id,
        }

        if status is not None:
            filters.append("status = :status")
            parameters["status"] = status

        return int(
            self.database.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM chat_sessions
                    WHERE {" AND ".join(filters)}
                    """
                ),
                parameters,
            ).scalar_one()
        )

    def update_session_title(
        self,
        *,
        session_id: int,
        user_id: int,
        title: str,
    ) -> ChatSessionRecord:
        self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
        )

        self.database.execute(
            text(
                """
                UPDATE chat_sessions
                SET
                    title = :title,
                    updated_at = UTC_TIMESTAMP()
                WHERE id = :session_id
                  AND user_id = :user_id
                """
            ),
            {
                "title": title,
                "session_id": session_id,
                "user_id": user_id,
            },
        )
        return self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
        )

    def update_selected_knowledge_base(
        self,
        *,
        session_id: int,
        user_id: int,
        knowledge_base_id: int | None,
    ) -> ChatSessionRecord:
        self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )

        if knowledge_base_id is not None:
            self.require_active_knowledge_base(
                knowledge_base_id
            )

        self.database.execute(
            text(
                """
                UPDATE chat_sessions
                SET
                    selected_knowledge_base_id =
                        :knowledge_base_id,
                    updated_at = UTC_TIMESTAMP()
                WHERE id = :session_id
                  AND user_id = :user_id
                """
            ),
            {
                "knowledge_base_id": knowledge_base_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        )
        return self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
        )

    def archive_session(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> ChatSessionRecord:
        self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
        )

        self.database.execute(
            text(
                """
                UPDATE chat_sessions
                SET
                    status = 'archived',
                    updated_at = UTC_TIMESTAMP()
                WHERE id = :session_id
                  AND user_id = :user_id
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
            },
        )
        return self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
        )

    def restore_session(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> ChatSessionRecord:
        self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=True,
        )

        self.database.execute(
            text(
                """
                UPDATE chat_sessions
                SET
                    status = 'active',
                    updated_at = UTC_TIMESTAMP()
                WHERE id = :session_id
                  AND user_id = :user_id
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
            },
        )
        return self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=True,
        )

    def add_message(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        user_id: int | None,
        reply_to_message_id: int | None = None,
        intent: str | None = None,
        routed_knowledge_base_id: int | None = None,
        retrieval_status: str | None = None,
        is_fallback: bool = False,
        question_char_count: int | None = None,
        prompt_token_estimate: int | None = None,
        completion_token_count: int | None = None,
        follow_up_suggestions: Sequence[str] | None = None,
        stream_completed_at: datetime | None = None,
    ) -> ChatMessageRecord:
        if routed_knowledge_base_id is not None:
            self.require_active_knowledge_base(
                routed_knowledge_base_id
            )

        suggestions_json = (
            json.dumps(
                list(follow_up_suggestions),
                ensure_ascii=False,
            )
            if follow_up_suggestions is not None
            else None
        )

        result = self.database.execute(
            text(
                """
                INSERT INTO chat_messages (
                    session_id,
                    user_id,
                    reply_to_message_id,
                    role,
                    content,
                    intent,
                    routed_knowledge_base_id,
                    retrieval_status,
                    is_fallback,
                    question_char_count,
                    prompt_token_estimate,
                    completion_token_count,
                    follow_up_suggestions,
                    stream_completed_at
                )
                VALUES (
                    :session_id,
                    :user_id,
                    :reply_to_message_id,
                    :role,
                    :content,
                    :intent,
                    :routed_knowledge_base_id,
                    :retrieval_status,
                    :is_fallback,
                    :question_char_count,
                    :prompt_token_estimate,
                    :completion_token_count,
                    :follow_up_suggestions,
                    :stream_completed_at
                )
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "reply_to_message_id": reply_to_message_id,
                "role": role,
                "content": content,
                "intent": intent,
                "routed_knowledge_base_id":
                    routed_knowledge_base_id,
                "retrieval_status": retrieval_status,
                "is_fallback": 1 if is_fallback else 0,
                "question_char_count": question_char_count,
                "prompt_token_estimate":
                    prompt_token_estimate,
                "completion_token_count":
                    completion_token_count,
                "follow_up_suggestions": suggestions_json,
                "stream_completed_at": stream_completed_at,
            },
        )
        message_id = int(result.lastrowid)

        self.database.execute(
            text(
                """
                UPDATE chat_sessions
                SET
                    last_message_at = UTC_TIMESTAMP(),
                    updated_at = UTC_TIMESTAMP()
                WHERE id = :session_id
                """
            ),
            {"session_id": session_id},
        )

        return self.require_message(message_id)

    def get_message(
        self,
        message_id: int,
    ) -> ChatMessageRecord | None:
        row = self.database.execute(
            text(
                """
                SELECT
                    id,
                    session_id,
                    user_id,
                    reply_to_message_id,
                    role,
                    content,
                    intent,
                    routed_knowledge_base_id,
                    retrieval_status,
                    is_fallback,
                    question_char_count,
                    prompt_token_estimate,
                    completion_token_count,
                    follow_up_suggestions,
                    stream_completed_at,
                    created_at,
                    updated_at
                FROM chat_messages
                WHERE id = :message_id
                LIMIT 1
                """
            ),
            {"message_id": message_id},
        ).mappings().first()

        return (
            self._message_from_mapping(row)
            if row is not None
            else None
        )

    def require_message(
        self,
        message_id: int,
    ) -> ChatMessageRecord:
        message = self.get_message(message_id)
        if message is None:
            raise LookupError("消息不存在")
        return message

    def list_messages_owned(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> list[ChatMessageRecord]:
        self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
        )

        rows = self.database.execute(
            text(
                """
                SELECT
                    id,
                    session_id,
                    user_id,
                    reply_to_message_id,
                    role,
                    content,
                    intent,
                    routed_knowledge_base_id,
                    retrieval_status,
                    is_fallback,
                    question_char_count,
                    prompt_token_estimate,
                    completion_token_count,
                    follow_up_suggestions,
                    stream_completed_at,
                    created_at,
                    updated_at
                FROM chat_messages
                WHERE session_id = :session_id
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"session_id": session_id},
        ).mappings().all()

        return [
            self._message_from_mapping(row)
            for row in rows
        ]

    def list_recent_messages_owned(
        self,
        *,
        session_id: int,
        user_id: int,
        max_messages: int,
    ) -> list[ChatMessageRecord]:
        self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
        )

        rows = self.database.execute(
            text(
                """
                SELECT *
                FROM (
                    SELECT
                        id,
                        session_id,
                        user_id,
                        reply_to_message_id,
                        role,
                        content,
                        intent,
                        routed_knowledge_base_id,
                        retrieval_status,
                        is_fallback,
                        question_char_count,
                        prompt_token_estimate,
                        completion_token_count,
                        follow_up_suggestions,
                        stream_completed_at,
                        created_at,
                        updated_at
                    FROM chat_messages
                    WHERE session_id = :session_id
                      AND role IN ('user', 'assistant')
                    ORDER BY created_at DESC, id DESC
                    LIMIT :max_messages
                ) AS recent_messages
                ORDER BY created_at ASC, id ASC
                """
            ),
            {
                "session_id": session_id,
                "max_messages": max_messages,
            },
        ).mappings().all()

        return [
            self._message_from_mapping(row)
            for row in rows
        ]

    def add_message_source(
        self,
        *,
        message_id: int,
        document_name: str,
        chunk_summary: str,
        rank: int,
        document_id: int | None = None,
        chunk_id: int | None = None,
        distance: float | None = None,
        similarity_score: float | None = None,
    ) -> MessageSourceRecord:
        result = self.database.execute(
            text(
                """
                INSERT INTO message_sources (
                    message_id,
                    document_id,
                    chunk_id,
                    document_name,
                    chunk_summary,
                    distance,
                    similarity_score,
                    `rank`
                )
                VALUES (
                    :message_id,
                    :document_id,
                    :chunk_id,
                    :document_name,
                    :chunk_summary,
                    :distance,
                    :similarity_score,
                    :rank
                )
                """
            ),
            {
                "message_id": message_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
                "document_name": document_name,
                "chunk_summary": chunk_summary,
                "distance": distance,
                "similarity_score": similarity_score,
                "rank": rank,
            },
        )
        source_id = int(result.lastrowid)
        return self.require_source(source_id)

    def list_message_sources_owned(
        self,
        *,
        message_id: int,
        user_id: int,
    ) -> list[MessageSourceRecord]:
        rows = self.database.execute(
            text(
                """
                SELECT
                    ms.id,
                    ms.message_id,
                    ms.document_id,
                    ms.chunk_id,
                    ms.document_name,
                    ms.chunk_summary,
                    ms.distance,
                    ms.similarity_score,
                    ms.`rank` AS `rank`,
                    ms.created_at
                FROM message_sources AS ms
                INNER JOIN chat_messages AS cm
                    ON cm.id = ms.message_id
                INNER JOIN chat_sessions AS cs
                    ON cs.id = cm.session_id
                WHERE ms.message_id = :message_id
                  AND cs.user_id = :user_id
                ORDER BY ms.`rank` ASC, ms.id ASC
                """
            ),
            {
                "message_id": message_id,
                "user_id": user_id,
            },
        ).mappings().all()

        return [
            self._source_from_mapping(row)
            for row in rows
        ]

    def require_source(
        self,
        source_id: int,
    ) -> MessageSourceRecord:
        row = self.database.execute(
            text(
                """
                SELECT
                    id,
                    message_id,
                    document_id,
                    chunk_id,
                    document_name,
                    chunk_summary,
                    distance,
                    similarity_score,
                    `rank`,
                    created_at
                FROM message_sources
                WHERE id = :source_id
                LIMIT 1
                """
            ),
            {"source_id": source_id},
        ).mappings().first()

        if row is None:
            raise LookupError("消息来源不存在")
        return self._source_from_mapping(row)

    def upsert_message_feedback(
        self,
        *,
        message_id: int,
        user_id: int,
        rating: int,
        comment: str | None,
    ) -> MessageFeedbackRecord:
        self.database.execute(
            text(
                """
                INSERT INTO message_feedback (
                    message_id,
                    user_id,
                    rating,
                    comment
                )
                VALUES (
                    :message_id,
                    :user_id,
                    :rating,
                    :comment
                )
                ON DUPLICATE KEY UPDATE
                    rating = :rating,
                    comment = :comment,
                    updated_at = UTC_TIMESTAMP()
                """
            ),
            {
                "message_id": message_id,
                "user_id": user_id,
                "rating": rating,
                "comment": comment,
            },
        )
        feedback = self.get_message_feedback(
            message_id=message_id,
            user_id=user_id,
        )
        if feedback is None:
            raise LookupError("反馈写入失败")
        return feedback

    def get_message_feedback(
        self,
        *,
        message_id: int,
        user_id: int,
    ) -> MessageFeedbackRecord | None:
        row = self.database.execute(
            text(
                """
                SELECT
                    id,
                    message_id,
                    user_id,
                    rating,
                    comment,
                    created_at,
                    updated_at
                FROM message_feedback
                WHERE message_id = :message_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {
                "message_id": message_id,
                "user_id": user_id,
            },
        ).mappings().first()

        return (
            self._feedback_from_mapping(row)
            if row is not None
            else None
        )

    def list_session_feedback_owned(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> list[MessageFeedbackRecord]:
        self.require_owned_session(
            session_id=session_id,
            user_id=user_id,
        )

        rows = self.database.execute(
            text(
                """
                SELECT
                    mf.id,
                    mf.message_id,
                    mf.user_id,
                    mf.rating,
                    mf.comment,
                    mf.created_at,
                    mf.updated_at
                FROM message_feedback AS mf
                INNER JOIN chat_messages AS cm
                    ON cm.id = mf.message_id
                WHERE cm.session_id = :session_id
                  AND mf.user_id = :user_id
                ORDER BY mf.created_at ASC, mf.id ASC
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
            },
        ).mappings().all()

        return [
            self._feedback_from_mapping(row)
            for row in rows
        ]

    def delete_message_feedback(
        self,
        *,
        message_id: int,
        user_id: int,
    ) -> bool:
        result = self.database.execute(
            text(
                """
                DELETE FROM message_feedback
                WHERE message_id = :message_id
                  AND user_id = :user_id
                """
            ),
            {
                "message_id": message_id,
                "user_id": user_id,
            },
        )
        return bool(result.rowcount)

    def try_consume_daily_question(
        self,
        *,
        user_id: int,
        daily_limit: int,
    ) -> int | None:
        """Atomically consume one question from today's per-user quota.

        Returns the new question count when consumption succeeds.
        Returns None when the configured daily limit has already been reached.
        The surrounding service owns commit/rollback so this repository method
        does not commit on its own.
        """
        if daily_limit <= 0:
            raise ValueError("daily_limit 必须大于 0")

        row = self.database.execute(
            text(
                """
                SELECT question_count
                FROM daily_question_usage
                WHERE user_id = :user_id
                  AND usage_date = CURRENT_DATE()
                LIMIT 1
                FOR UPDATE
                """
            ),
            {"user_id": user_id},
        ).mappings().first()

        if row is None:
            self.database.execute(
                text(
                    """
                    INSERT INTO daily_question_usage (
                        user_id,
                        usage_date,
                        question_count
                    )
                    VALUES (
                        :user_id,
                        CURRENT_DATE(),
                        1
                    )
                    """
                ),
                {"user_id": user_id},
            )
            return 1

        current_count = int(row["question_count"])
        if current_count >= daily_limit:
            return None

        next_count = current_count + 1
        self.database.execute(
            text(
                """
                UPDATE daily_question_usage
                SET
                    question_count = :question_count,
                    updated_at = UTC_TIMESTAMP()
                WHERE user_id = :user_id
                  AND usage_date = CURRENT_DATE()
                """
            ),
            {
                "question_count": next_count,
                "user_id": user_id,
            },
        )
        return next_count

    def get_today_question_count(
        self,
        *,
        user_id: int,
    ) -> int:
        """Return today's persisted question count for one user."""
        value = self.database.execute(
            text(
                """
                SELECT question_count
                FROM daily_question_usage
                WHERE user_id = :user_id
                  AND usage_date = CURRENT_DATE()
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).scalar_one_or_none()

        return int(value) if value is not None else 0

    def require_active_knowledge_base(
        self,
        knowledge_base_id: int,
    ) -> None:
        value = self.database.execute(
            text(
                """
                SELECT id
                FROM knowledge_bases
                WHERE id = :knowledge_base_id
                  AND is_active = 1
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"knowledge_base_id": knowledge_base_id},
        ).scalar_one_or_none()

        if value is None:
            raise LookupError(
                "知识库不存在、已停用或已删除"
            )

    def commit(self) -> None:
        self.database.commit()

    def rollback(self) -> None:
        self.database.rollback()

    @staticmethod
    def _session_from_mapping(
        row: Any,
    ) -> ChatSessionRecord:
        return ChatSessionRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            title=str(row["title"]),
            status=str(row["status"]),
            selected_knowledge_base_id=(
                int(row["selected_knowledge_base_id"])
                if row["selected_knowledge_base_id"] is not None
                else None
            ),
            last_message_at=row["last_message_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _message_from_mapping(
        row: Any,
    ) -> ChatMessageRecord:
        raw_suggestions = row["follow_up_suggestions"]
        suggestions: list[str] | None

        if raw_suggestions is None:
            suggestions = None
        elif isinstance(raw_suggestions, list):
            suggestions = [
                str(item)
                for item in raw_suggestions
            ]
        else:
            parsed = json.loads(str(raw_suggestions))
            suggestions = [
                str(item)
                for item in parsed
            ]

        return ChatMessageRecord(
            id=int(row["id"]),
            session_id=int(row["session_id"]),
            user_id=(
                int(row["user_id"])
                if row["user_id"] is not None
                else None
            ),
            reply_to_message_id=(
                int(row["reply_to_message_id"])
                if row["reply_to_message_id"] is not None
                else None
            ),
            role=str(row["role"]),
            content=str(row["content"]),
            intent=(
                str(row["intent"])
                if row["intent"] is not None
                else None
            ),
            routed_knowledge_base_id=(
                int(row["routed_knowledge_base_id"])
                if row["routed_knowledge_base_id"] is not None
                else None
            ),
            retrieval_status=(
                str(row["retrieval_status"])
                if row["retrieval_status"] is not None
                else None
            ),
            is_fallback=bool(row["is_fallback"]),
            question_char_count=(
                int(row["question_char_count"])
                if row["question_char_count"] is not None
                else None
            ),
            prompt_token_estimate=(
                int(row["prompt_token_estimate"])
                if row["prompt_token_estimate"] is not None
                else None
            ),
            completion_token_count=(
                int(row["completion_token_count"])
                if row["completion_token_count"] is not None
                else None
            ),
            follow_up_suggestions=suggestions,
            stream_completed_at=row["stream_completed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _feedback_from_mapping(
        row: Any,
    ) -> MessageFeedbackRecord:
        return MessageFeedbackRecord(
            id=int(row["id"]),
            message_id=int(row["message_id"]),
            user_id=int(row["user_id"]),
            rating=int(row["rating"]),
            comment=(
                str(row["comment"])
                if row["comment"] is not None
                else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _source_from_mapping(
        row: Any,
    ) -> MessageSourceRecord:
        return MessageSourceRecord(
            id=int(row["id"]),
            message_id=int(row["message_id"]),
            document_id=(
                int(row["document_id"])
                if row["document_id"] is not None
                else None
            ),
            chunk_id=(
                int(row["chunk_id"])
                if row["chunk_id"] is not None
                else None
            ),
            document_name=str(row["document_name"]),
            chunk_summary=str(row["chunk_summary"]),
            distance=(
                float(row["distance"])
                if row["distance"] is not None
                else None
            ),
            similarity_score=(
                float(row["similarity_score"])
                if row["similarity_score"] is not None
                else None
            ),
            rank=int(row["rank"]),
            created_at=row["created_at"],
        )
