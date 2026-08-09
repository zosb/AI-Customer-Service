from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import AdminServiceDep, CurrentAdmin
from app.schemas.admin import (
    AdminFeedbackListResponse,
    AdminFeedbackPublic,
    AdminFeedbackSummaryResponse,
    AdminMessagePublic,
    AdminOverviewResponse,
    AdminSessionDetailResponse,
    AdminSessionListResponse,
    AdminSessionPublic,
    DailyQuestionTrendResponse,
)
from app.services.admin.service import AdminValidationError

router = APIRouter(
    prefix="/admin",
    tags=["管理后台"],
)


def _session_public(item) -> AdminSessionPublic:
    return AdminSessionPublic(**item.__dict__)


@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="获取管理后台总览指标",
)
def get_admin_overview(
    current_admin: CurrentAdmin,
    service: AdminServiceDep,
) -> AdminOverviewResponse:
    del current_admin
    try:
        return AdminOverviewResponse(**service.get_overview())
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="管理后台统计查询失败",
        ) from exc


@router.get(
    "/sessions",
    response_model=AdminSessionListResponse,
    summary="查看全量会话记录",
)
def list_admin_sessions(
    current_admin: CurrentAdmin,
    service: AdminServiceDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(active|archived)$",
    ),
    q: str | None = Query(default=None, max_length=100),
) -> AdminSessionListResponse:
    del current_admin
    try:
        items, total = service.list_sessions(
            limit=limit,
            offset=offset,
            status=session_status,
            query=q,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="全量会话查询失败",
        ) from exc

    return AdminSessionListResponse(
        items=[_session_public(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=AdminSessionDetailResponse,
    summary="查看任意会话完整记录",
)
def get_admin_session_detail(
    session_id: int,
    current_admin: CurrentAdmin,
    service: AdminServiceDep,
) -> AdminSessionDetailResponse:
    del current_admin
    try:
        detail = service.get_session_detail(session_id)
    except AdminValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="会话详情查询失败",
        ) from exc

    return AdminSessionDetailResponse(
        session=_session_public(detail.session),
        messages=[
            AdminMessagePublic(**item.__dict__)
            for item in detail.messages
        ],
    )


@router.get(
    "/feedback/summary",
    response_model=AdminFeedbackSummaryResponse,
    summary="获取用户反馈统计",
)
def get_admin_feedback_summary(
    current_admin: CurrentAdmin,
    service: AdminServiceDep,
) -> AdminFeedbackSummaryResponse:
    del current_admin
    try:
        return AdminFeedbackSummaryResponse(
            **service.get_feedback_summary()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="用户反馈统计查询失败",
        ) from exc


@router.get(
    "/feedback",
    response_model=AdminFeedbackListResponse,
    summary="获取用户反馈明细",
)
def list_admin_feedback(
    current_admin: CurrentAdmin,
    service: AdminServiceDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminFeedbackListResponse:
    del current_admin
    try:
        items, total = service.list_feedback(
            limit=limit,
            offset=offset,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="用户反馈明细查询失败",
        ) from exc

    return AdminFeedbackListResponse(
        items=[
            AdminFeedbackPublic(**item.__dict__)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/analytics/daily-questions",
    response_model=DailyQuestionTrendResponse,
    summary="获取日均问答量趋势",
)
def get_daily_question_trend(
    current_admin: CurrentAdmin,
    service: AdminServiceDep,
    days: int = Query(default=14, ge=1, le=90),
) -> DailyQuestionTrendResponse:
    del current_admin
    try:
        return DailyQuestionTrendResponse(
            **service.get_daily_question_trend(days=days)
        )
    except AdminValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="问答趋势统计查询失败",
        ) from exc
