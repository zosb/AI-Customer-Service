from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class AdminOverviewResponse(BaseModel):
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
    satisfaction_rate: float
    prompt_token_estimate: int
    completion_token_count: int


class AdminSessionPublic(BaseModel):
    id: int
    user_id: int
    user_label: str
    title: str
    status: Literal["active", "archived"]
    selected_knowledge_base_id: int | None
    message_count: int
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminSessionListResponse(BaseModel):
    items: list[AdminSessionPublic]
    total: int
    limit: int
    offset: int


class AdminMessagePublic(BaseModel):
    id: int
    role: Literal["user", "assistant", "system"]
    content: str
    intent: str | None
    routed_knowledge_base_id: int | None
    retrieval_status: str | None
    is_fallback: bool
    feedback_rating: Literal[-1, 1] | None
    feedback_comment: str | None
    created_at: datetime


class AdminSessionDetailResponse(BaseModel):
    session: AdminSessionPublic
    messages: list[AdminMessagePublic]


class AdminFeedbackIntentStat(BaseModel):
    intent: str
    total: int
    positive: int
    negative: int
    satisfaction_rate: float


class AdminFeedbackSummaryResponse(BaseModel):
    total: int
    positive: int
    negative: int
    satisfaction_rate: float
    by_intent: list[AdminFeedbackIntentStat]


class AdminFeedbackPublic(BaseModel):
    id: int
    message_id: int
    session_id: int
    session_title: str
    user_id: int
    user_label: str
    rating: Literal[-1, 1]
    comment: str | None
    intent: str | None
    assistant_content: str
    created_at: datetime


class AdminFeedbackListResponse(BaseModel):
    items: list[AdminFeedbackPublic]
    total: int
    limit: int
    offset: int


class DailyQuestionPoint(BaseModel):
    date: date
    question_count: int


class DailyQuestionTrendResponse(BaseModel):
    days: int
    total_questions: int
    average_per_day: float
    items: list[DailyQuestionPoint]
