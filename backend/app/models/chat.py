from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ChatSession(TimestampMixin, Base):
    """每次独立对话对应一个 Session。"""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_chat_sessions_status",
        ),
        Index(
            "ix_chat_sessions_user_last_message",
            "user_id",
            "last_message_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'新会话'"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
    )
    selected_knowledge_base_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


class ChatMessage(TimestampMixin, Base):
    """用户、AI 与系统消息。"""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_chat_messages_role",
        ),
        CheckConstraint(
            """
            retrieval_status IS NULL OR
            retrieval_status IN ('matched', 'empty', 'skipped', 'failed')
            """,
            name="ck_chat_messages_retrieval_status",
        ),
        Index(
            "ix_chat_messages_session_created",
            "session_id",
            "created_at",
        ),
        Index(
            "ix_chat_messages_intent",
            "intent",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reply_to_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    routed_knowledge_base_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )
    retrieval_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    is_fallback: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    question_char_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    prompt_token_estimate: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    completion_token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    follow_up_suggestions: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    stream_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


class MessageSource(Base):
    """AI 回答引用的知识来源快照。"""

    __tablename__ = "message_sources"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "rank",
            name="uq_message_sources_message_rank",
        ),
        Index(
            "ix_message_sources_document",
            "document_id",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_summary: Mapped[str] = mapped_column(Text, nullable=False)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class MessageFeedback(TimestampMixin, Base):
    """用户对 AI 回答的点赞、点踩和文字反馈。"""

    __tablename__ = "message_feedback"
    __table_args__ = (
        CheckConstraint(
            "rating IN (-1, 1)",
            name="ck_message_feedback_rating",
        ),
        UniqueConstraint(
            "message_id",
            "user_id",
            name="uq_message_feedback_message_user",
        ),
        Index(
            "ix_message_feedback_rating_created",
            "rating",
            "created_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
