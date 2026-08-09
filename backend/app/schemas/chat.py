from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatSessionCreateRequest(BaseModel):
    title: str = Field(
        default="新会话",
        max_length=255,
    )
    selected_knowledge_base_id: int | None = Field(
        default=None,
        gt=0,
    )


class ChatSessionUpdateRequest(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=255,
    )
    selected_knowledge_base_id: int | None = Field(
        default=None,
        gt=0,
    )
    clear_selected_knowledge_base: bool = False


class ChatSessionPublic(BaseModel):
    id: int
    user_id: int
    title: str
    status: Literal["active", "archived"]
    selected_knowledge_base_id: int | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionPublic]
    total: int
    limit: int
    offset: int


class ChatMessagePublic(BaseModel):
    id: int
    session_id: int
    user_id: int | None
    reply_to_message_id: int | None
    role: Literal["user", "assistant", "system"]
    content: str
    intent: str | None
    routed_knowledge_base_id: int | None
    retrieval_status: (
        Literal[
            "matched",
            "empty",
            "skipped",
            "failed",
        ]
        | None
    )
    is_fallback: bool
    question_char_count: int | None
    prompt_token_estimate: int | None
    completion_token_count: int | None
    follow_up_suggestions: list[str] | None
    stream_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChatMessageHistoryResponse(BaseModel):
    session: ChatSessionPublic
    messages: list[ChatMessagePublic]


class MessageSourcePublic(BaseModel):
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


class ChatSessionArchiveResponse(BaseModel):
    session_id: int
    status: Literal["archived"] = "archived"


class ChatStreamRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=500,
        description="当前用户问题，业务限制最多 500 字",
    )


class MessageFeedbackRequest(BaseModel):
    rating: Literal[-1, 1] = Field(
        description="1=点赞，-1=点踩",
    )
    comment: str | None = Field(
        default=None,
        max_length=1000,
        description="可选文字反馈",
    )


class MessageFeedbackPublic(BaseModel):
    id: int
    message_id: int
    user_id: int
    rating: Literal[-1, 1]
    comment: str | None
    created_at: datetime
    updated_at: datetime


class MessageFeedbackDeleteResponse(BaseModel):
    message_id: int
    status: Literal["deleted", "not_found"]
