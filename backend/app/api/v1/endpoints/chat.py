from __future__ import annotations

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import StreamingResponse

from app.api.deps import (
    ChatSessionServiceDep,
    ChatStreamingAnswerServiceDep,
    CurrentUser,
)
from app.repositories.chat_repository import (
    ChatMessageRecord,
    ChatSessionRecord,
    MessageFeedbackRecord,
    MessageSourceRecord,
)
from app.schemas.chat import (
    ChatMessageHistoryResponse,
    ChatMessagePublic,
    ChatSessionArchiveResponse,
    ChatSessionCreateRequest,
    ChatSessionListResponse,
    ChatSessionPublic,
    ChatSessionUpdateRequest,
    MessageSourcePublic,
    ChatStreamRequest,
    MessageFeedbackDeleteResponse,
    MessageFeedbackPublic,
    MessageFeedbackRequest,
)
from app.services.chat.answer_service import DailyQuestionLimitError
from app.services.chat.session_service import (
    ChatMessageNotFoundError,
    ChatSessionNotFoundError,
    ChatValidationError,
)

router = APIRouter(
    prefix="/chat",
    tags=["客服会话"],
)


def _session_public(
    item: ChatSessionRecord,
) -> ChatSessionPublic:
    return ChatSessionPublic(
        id=item.id,
        user_id=item.user_id,
        title=item.title,
        status=item.status,  # type: ignore[arg-type]
        selected_knowledge_base_id=(
            item.selected_knowledge_base_id
        ),
        last_message_at=item.last_message_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _message_public(
    item: ChatMessageRecord,
) -> ChatMessagePublic:
    return ChatMessagePublic(
        id=item.id,
        session_id=item.session_id,
        user_id=item.user_id,
        reply_to_message_id=item.reply_to_message_id,
        role=item.role,  # type: ignore[arg-type]
        content=item.content,
        intent=item.intent,
        routed_knowledge_base_id=(
            item.routed_knowledge_base_id
        ),
        retrieval_status=(
            item.retrieval_status  # type: ignore[arg-type]
        ),
        is_fallback=item.is_fallback,
        question_char_count=item.question_char_count,
        prompt_token_estimate=item.prompt_token_estimate,
        completion_token_count=item.completion_token_count,
        follow_up_suggestions=item.follow_up_suggestions,
        stream_completed_at=item.stream_completed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _source_public(
    item: MessageSourceRecord,
) -> MessageSourcePublic:
    return MessageSourcePublic(
        id=item.id,
        message_id=item.message_id,
        document_id=item.document_id,
        chunk_id=item.chunk_id,
        document_name=item.document_name,
        chunk_summary=item.chunk_summary,
        distance=item.distance,
        similarity_score=item.similarity_score,
        rank=item.rank,
        created_at=item.created_at,
    )


def _feedback_public(
    item: MessageFeedbackRecord,
) -> MessageFeedbackPublic:
    return MessageFeedbackPublic(
        id=item.id,
        message_id=item.message_id,
        user_id=item.user_id,
        rating=item.rating,  # type: ignore[arg-type]
        comment=item.comment,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _raise_chat_error(exc: Exception) -> None:
    if isinstance(
        exc,
        (ChatSessionNotFoundError, ChatMessageNotFoundError),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, ChatValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    raise exc


@router.post(
    "/sessions",
    response_model=ChatSessionPublic,
    status_code=status.HTTP_201_CREATED,
    summary="创建客服会话",
)
def create_session(
    payload: ChatSessionCreateRequest,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> ChatSessionPublic:
    try:
        item = service.create_session(
            user_id=current_user.id,
            title=payload.title,
            selected_knowledge_base_id=(
                payload.selected_knowledge_base_id
            ),
        )
        return _session_public(item)
    except (
        ChatSessionNotFoundError,
        ChatValidationError,
    ) as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    summary="获取当前用户的会话列表",
)
def list_sessions(
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
    session_status: str | None = Query(
        default=None,
        alias="status",
        description="可选：active 或 archived",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ChatSessionListResponse:
    try:
        items = service.list_sessions(
            user_id=current_user.id,
            status=session_status,
            limit=limit,
            offset=offset,
        )
        total = service.count_sessions(
            user_id=current_user.id,
            status=session_status,
        )

        return ChatSessionListResponse(
            items=[
                _session_public(item)
                for item in items
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
    except ChatValidationError as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionPublic,
    summary="获取会话详情",
)
def get_session(
    session_id: int,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> ChatSessionPublic:
    try:
        return _session_public(
            service.get_session(
                session_id=session_id,
                user_id=current_user.id,
            )
        )
    except ChatSessionNotFoundError as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionPublic,
    summary="修改会话标题或选择知识库",
)
def update_session(
    session_id: int,
    payload: ChatSessionUpdateRequest,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> ChatSessionPublic:
    if (
        payload.title is None
        and payload.selected_knowledge_base_id is None
        and not payload.clear_selected_knowledge_base
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="至少提供一个需要修改的字段",
        )

    try:
        item = service.get_session(
            session_id=session_id,
            user_id=current_user.id,
        )

        if payload.title is not None:
            item = service.rename_session(
                session_id=session_id,
                user_id=current_user.id,
                title=payload.title,
            )

        if (
            payload.selected_knowledge_base_id is not None
            or payload.clear_selected_knowledge_base
        ):
            item = service.select_knowledge_base(
                session_id=session_id,
                user_id=current_user.id,
                knowledge_base_id=(
                    None
                    if payload.clear_selected_knowledge_base
                    else payload.selected_knowledge_base_id
                ),
            )

        return _session_public(item)
    except (
        ChatSessionNotFoundError,
        ChatValidationError,
    ) as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.delete(
    "/sessions/{session_id}",
    response_model=ChatSessionArchiveResponse,
    summary="归档客服会话",
)
def archive_session(
    session_id: int,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> ChatSessionArchiveResponse:
    try:
        item = service.archive_session(
            session_id=session_id,
            user_id=current_user.id,
        )
        return ChatSessionArchiveResponse(
            session_id=item.id,
        )
    except ChatSessionNotFoundError as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/sessions/{session_id}/restore",
    response_model=ChatSessionPublic,
    summary="恢复已归档客服会话",
)
def restore_session(
    session_id: int,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> ChatSessionPublic:
    try:
        item = service.restore_session(
            session_id=session_id,
            user_id=current_user.id,
        )
        return _session_public(item)
    except ChatSessionNotFoundError as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageHistoryResponse,
    summary="获取完整会话消息历史",
)
def list_messages(
    session_id: int,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> ChatMessageHistoryResponse:
    try:
        session = service.get_session(
            session_id=session_id,
            user_id=current_user.id,
        )
        messages = service.list_messages(
            session_id=session_id,
            user_id=current_user.id,
        )

        return ChatMessageHistoryResponse(
            session=_session_public(session),
            messages=[
                _message_public(item)
                for item in messages
            ],
        )
    except ChatSessionNotFoundError as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/messages/{message_id}/sources",
    response_model=list[MessageSourcePublic],
    summary="获取 AI 消息的知识来源",
)
def list_message_sources(
    message_id: int,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> list[MessageSourcePublic]:
    items = service.list_message_sources(
        message_id=message_id,
        user_id=current_user.id,
    )
    return [
        _source_public(item)
        for item in items
    ]


@router.get(
    "/sessions/{session_id}/feedback",
    response_model=list[MessageFeedbackPublic],
    summary="获取当前用户在会话中的 AI 回答反馈",
)
def list_session_feedback(
    session_id: int,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> list[MessageFeedbackPublic]:
    try:
        items = service.list_session_feedback(
            session_id=session_id,
            user_id=current_user.id,
        )
        return [
            _feedback_public(item)
            for item in items
        ]
    except (
        ChatSessionNotFoundError,
        ChatValidationError,
    ) as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.put(
    "/messages/{message_id}/feedback",
    response_model=MessageFeedbackPublic,
    summary="提交或更新 AI 回答反馈",
)
def submit_message_feedback(
    message_id: int,
    payload: MessageFeedbackRequest,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> MessageFeedbackPublic:
    try:
        item = service.submit_message_feedback(
            message_id=message_id,
            user_id=current_user.id,
            rating=payload.rating,
            comment=payload.comment,
        )
        return _feedback_public(item)
    except (
        ChatMessageNotFoundError,
        ChatSessionNotFoundError,
        ChatValidationError,
    ) as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.delete(
    "/messages/{message_id}/feedback",
    response_model=MessageFeedbackDeleteResponse,
    summary="撤销当前用户对 AI 回答的反馈",
)
def delete_message_feedback(
    message_id: int,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
) -> MessageFeedbackDeleteResponse:
    try:
        deleted = service.delete_message_feedback(
            message_id=message_id,
            user_id=current_user.id,
        )
        return MessageFeedbackDeleteResponse(
            message_id=message_id,
            status=(
                "deleted"
                if deleted
                else "not_found"
            ),
        )
    except (
        ChatMessageNotFoundError,
        ChatSessionNotFoundError,
        ChatValidationError,
    ) as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/sessions/{session_id}/messages",
    summary="发送客服问题并以 SSE 流式返回 AI 回答",
    responses={
        200: {
            "description": (
                "text/event-stream：meta / delta / replace / "
                "sources / done / error"
            ),
            "content": {
                "text/event-stream": {}
            },
        },
        401: {"description": "未登录或 JWT 无效"},
        404: {"description": "会话不存在或无权访问"},
        422: {"description": "问题参数或业务状态无效"},
        429: {"description": "达到每日问题上限"},
    },
)
def stream_chat_message(
    session_id: int,
    payload: ChatStreamRequest,
    current_user: CurrentUser,
    service: ChatStreamingAnswerServiceDep,
) -> StreamingResponse:
    try:
        plan = service.prepare(
            session_id=session_id,
            user_id=current_user.id,
            question=payload.question,
        )
    except DailyQuestionLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except (
        ChatSessionNotFoundError,
        ChatValidationError,
    ) as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable")

    return StreamingResponse(
        service.iter_sse(plan),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
