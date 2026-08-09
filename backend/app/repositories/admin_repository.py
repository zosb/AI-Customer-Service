from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.chat import (
    ChatMessage,
    ChatSession,
    MessageFeedback,
)
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.models.usage import DailyQuestionUsage
from app.models.user import User


@dataclass(frozen=True)
class AdminOverviewRecord:
    total_users: int
    active_users: int
    total_sessions: int
    active_sessions: int
    total_messages: int
    today_questions: int
    total_knowledge_bases: int
    total_documents: int
    feedback_total: int
    positive_feedback: int
    negative_feedback: int
    prompt_token_estimate: int
    completion_token_count: int


@dataclass(frozen=True)
class AdminSessionRecord:
    id: int
    user_id: int
    user_label: str
    title: str
    status: str
    selected_knowledge_base_id: int | None
    message_count: int
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AdminMessageRecord:
    id: int
    role: str
    content: str
    intent: str | None
    routed_knowledge_base_id: int | None
    retrieval_status: str | None
    is_fallback: bool
    feedback_rating: int | None
    feedback_comment: str | None
    created_at: datetime


@dataclass(frozen=True)
class AdminSessionDetailRecord:
    session: AdminSessionRecord
    messages: tuple[AdminMessageRecord, ...]


@dataclass(frozen=True)
class AdminFeedbackBreakdownRecord:
    intent: str
    total: int
    positive: int
    negative: int


@dataclass(frozen=True)
class AdminFeedbackRecord:
    id: int
    message_id: int
    session_id: int
    session_title: str
    user_id: int
    user_label: str
    rating: int
    comment: str | None
    intent: str | None
    assistant_content: str
    created_at: datetime


@dataclass(frozen=True)
class DailyQuestionRecord:
    usage_date: date
    question_count: int


def _user_label(
    *,
    user_id: int,
    display_name: str | None,
    email: str | None,
    phone: str | None,
) -> str:
    return (
        display_name
        or email
        or phone
        or f"用户#{user_id}"
    )


class AdminRepository:
    """管理后台只读统计与全量会话查询。"""

    def __init__(self, database: Session) -> None:
        self.database = database

    def get_overview(self, *, today: date) -> AdminOverviewRecord:
        total_users = int(
            self.database.scalar(select(func.count(User.id))) or 0
        )
        active_users = int(
            self.database.scalar(
                select(func.count(User.id)).where(User.status == "active")
            )
            or 0
        )
        total_sessions = int(
            self.database.scalar(select(func.count(ChatSession.id))) or 0
        )
        active_sessions = int(
            self.database.scalar(
                select(func.count(ChatSession.id)).where(
                    ChatSession.status == "active"
                )
            )
            or 0
        )
        total_messages = int(
            self.database.scalar(select(func.count(ChatMessage.id))) or 0
        )
        today_questions = int(
            self.database.scalar(
                select(func.coalesce(func.sum(DailyQuestionUsage.question_count), 0)).where(
                    DailyQuestionUsage.usage_date == today
                )
            )
            or 0
        )
        total_knowledge_bases = int(
            self.database.scalar(
                select(func.count(KnowledgeBase.id)).where(
                    KnowledgeBase.deleted_at.is_(None)
                )
            )
            or 0
        )
        total_documents = int(
            self.database.scalar(
                select(func.count(KnowledgeDocument.id)).where(
                    KnowledgeDocument.deleted_at.is_(None)
                )
            )
            or 0
        )

        feedback_row = self.database.execute(
            select(
                func.count(MessageFeedback.id),
                func.coalesce(
                    func.sum(
                        case((MessageFeedback.rating == 1, 1), else_=0)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case((MessageFeedback.rating == -1, 1), else_=0)
                    ),
                    0,
                ),
            )
        ).one()

        token_row = self.database.execute(
            select(
                func.coalesce(func.sum(ChatMessage.prompt_token_estimate), 0),
                func.coalesce(func.sum(ChatMessage.completion_token_count), 0),
            ).where(ChatMessage.role == "assistant")
        ).one()

        return AdminOverviewRecord(
            total_users=total_users,
            active_users=active_users,
            total_sessions=total_sessions,
            active_sessions=active_sessions,
            total_messages=total_messages,
            today_questions=today_questions,
            total_knowledge_bases=total_knowledge_bases,
            total_documents=total_documents,
            feedback_total=int(feedback_row[0] or 0),
            positive_feedback=int(feedback_row[1] or 0),
            negative_feedback=int(feedback_row[2] or 0),
            prompt_token_estimate=int(token_row[0] or 0),
            completion_token_count=int(token_row[1] or 0),
        )

    def list_sessions(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        query: str | None = None,
    ) -> tuple[list[AdminSessionRecord], int]:
        message_count = (
            select(func.count(ChatMessage.id))
            .where(ChatMessage.session_id == ChatSession.id)
            .correlate(ChatSession)
            .scalar_subquery()
        )

        conditions = []
        if status is not None:
            conditions.append(ChatSession.status == status)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    ChatSession.title.ilike(pattern),
                    User.display_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.phone.ilike(pattern),
                )
            )

        statement = (
            select(
                ChatSession,
                User.display_name,
                User.email,
                User.phone,
                message_count.label("message_count"),
            )
            .join(User, User.id == ChatSession.user_id)
            .where(*conditions)
            .order_by(
                ChatSession.last_message_at.desc(),
                ChatSession.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = self.database.execute(statement).all()

        count_statement = (
            select(func.count(ChatSession.id))
            .join(User, User.id == ChatSession.user_id)
            .where(*conditions)
        )
        total = int(self.database.scalar(count_statement) or 0)

        items = [
            AdminSessionRecord(
                id=row[0].id,
                user_id=row[0].user_id,
                user_label=_user_label(
                    user_id=row[0].user_id,
                    display_name=row[1],
                    email=row[2],
                    phone=row[3],
                ),
                title=row[0].title,
                status=row[0].status,
                selected_knowledge_base_id=(
                    row[0].selected_knowledge_base_id
                ),
                message_count=int(row[4] or 0),
                last_message_at=row[0].last_message_at,
                created_at=row[0].created_at,
                updated_at=row[0].updated_at,
            )
            for row in rows
        ]
        return items, total

    def get_session_detail(
        self,
        session_id: int,
    ) -> AdminSessionDetailRecord | None:
        row = self.database.execute(
            select(
                ChatSession,
                User.display_name,
                User.email,
                User.phone,
            )
            .join(User, User.id == ChatSession.user_id)
            .where(ChatSession.id == session_id)
        ).first()
        if row is None:
            return None

        session = row[0]
        message_rows = self.database.execute(
            select(
                ChatMessage,
                MessageFeedback.rating,
                MessageFeedback.comment,
            )
            .outerjoin(
                MessageFeedback,
                MessageFeedback.message_id == ChatMessage.id,
            )
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
        ).all()

        messages = tuple(
            AdminMessageRecord(
                id=message.id,
                role=message.role,
                content=message.content,
                intent=message.intent,
                routed_knowledge_base_id=(
                    message.routed_knowledge_base_id
                ),
                retrieval_status=message.retrieval_status,
                is_fallback=bool(message.is_fallback),
                feedback_rating=(
                    int(feedback_rating)
                    if feedback_rating is not None
                    else None
                ),
                feedback_comment=feedback_comment,
                created_at=message.created_at,
            )
            for message, feedback_rating, feedback_comment in message_rows
        )

        session_record = AdminSessionRecord(
            id=session.id,
            user_id=session.user_id,
            user_label=_user_label(
                user_id=session.user_id,
                display_name=row[1],
                email=row[2],
                phone=row[3],
            ),
            title=session.title,
            status=session.status,
            selected_knowledge_base_id=(
                session.selected_knowledge_base_id
            ),
            message_count=len(messages),
            last_message_at=session.last_message_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        return AdminSessionDetailRecord(
            session=session_record,
            messages=messages,
        )

    def get_feedback_breakdown(
        self,
    ) -> list[AdminFeedbackBreakdownRecord]:
        intent_label = func.coalesce(ChatMessage.intent, "unknown")
        rows = self.database.execute(
            select(
                intent_label.label("intent"),
                func.count(MessageFeedback.id),
                func.coalesce(
                    func.sum(
                        case((MessageFeedback.rating == 1, 1), else_=0)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case((MessageFeedback.rating == -1, 1), else_=0)
                    ),
                    0,
                ),
            )
            .join(
                ChatMessage,
                ChatMessage.id == MessageFeedback.message_id,
            )
            .group_by(intent_label)
            .order_by(func.count(MessageFeedback.id).desc())
        ).all()

        return [
            AdminFeedbackBreakdownRecord(
                intent=str(row[0]),
                total=int(row[1] or 0),
                positive=int(row[2] or 0),
                negative=int(row[3] or 0),
            )
            for row in rows
        ]

    def list_feedback(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AdminFeedbackRecord], int]:
        rows = self.database.execute(
            select(
                MessageFeedback,
                ChatMessage.intent,
                ChatMessage.content,
                ChatSession.id,
                ChatSession.title,
                User.display_name,
                User.email,
                User.phone,
            )
            .join(
                ChatMessage,
                ChatMessage.id == MessageFeedback.message_id,
            )
            .join(
                ChatSession,
                ChatSession.id == ChatMessage.session_id,
            )
            .join(User, User.id == MessageFeedback.user_id)
            .order_by(MessageFeedback.created_at.desc(), MessageFeedback.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        total = int(
            self.database.scalar(select(func.count(MessageFeedback.id))) or 0
        )

        items = [
            AdminFeedbackRecord(
                id=feedback.id,
                message_id=feedback.message_id,
                session_id=int(session_id),
                session_title=str(session_title),
                user_id=feedback.user_id,
                user_label=_user_label(
                    user_id=feedback.user_id,
                    display_name=display_name,
                    email=email,
                    phone=phone,
                ),
                rating=int(feedback.rating),
                comment=feedback.comment,
                intent=intent,
                assistant_content=content,
                created_at=feedback.created_at,
            )
            for (
                feedback,
                intent,
                content,
                session_id,
                session_title,
                display_name,
                email,
                phone,
            ) in rows
        ]
        return items, total

    def list_daily_questions(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[DailyQuestionRecord]:
        rows = self.database.execute(
            select(
                DailyQuestionUsage.usage_date,
                func.coalesce(
                    func.sum(DailyQuestionUsage.question_count),
                    0,
                ),
            )
            .where(
                DailyQuestionUsage.usage_date >= start_date,
                DailyQuestionUsage.usage_date <= end_date,
            )
            .group_by(DailyQuestionUsage.usage_date)
            .order_by(DailyQuestionUsage.usage_date)
        ).all()

        return [
            DailyQuestionRecord(
                usage_date=row[0],
                question_count=int(row[1] or 0),
            )
            for row in rows
        ]
