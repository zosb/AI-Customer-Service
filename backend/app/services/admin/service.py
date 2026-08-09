from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

from app.repositories.admin_repository import (
    AdminFeedbackBreakdownRecord,
    AdminFeedbackRecord,
    AdminOverviewRecord,
    AdminSessionDetailRecord,
    AdminSessionRecord,
    DailyQuestionRecord,
)


class AdminRepositoryProtocol(Protocol):
    def get_overview(self, *, today: date) -> AdminOverviewRecord: ...

    def list_sessions(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        query: str | None = None,
    ) -> tuple[list[AdminSessionRecord], int]: ...

    def get_session_detail(
        self,
        session_id: int,
    ) -> AdminSessionDetailRecord | None: ...

    def get_feedback_breakdown(
        self,
    ) -> list[AdminFeedbackBreakdownRecord]: ...

    def list_feedback(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AdminFeedbackRecord], int]: ...

    def list_daily_questions(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[DailyQuestionRecord]: ...


class AdminValidationError(ValueError):
    pass


class AdminService:
    def __init__(self, repository: AdminRepositoryProtocol) -> None:
        self.repository = repository

    @staticmethod
    def _rate(positive: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round(positive * 100.0 / total, 2)

    def get_overview(self, *, today: date | None = None) -> dict[str, object]:
        current_date = today or date.today()
        record = self.repository.get_overview(today=current_date)
        return {
            **record.__dict__,
            "satisfaction_rate": self._rate(
                record.positive_feedback,
                record.feedback_total,
            ),
        }

    def list_sessions(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None,
        query: str | None,
    ) -> tuple[list[AdminSessionRecord], int]:
        normalized_query = query.strip() if query else None
        return self.repository.list_sessions(
            limit=limit,
            offset=offset,
            status=status,
            query=normalized_query or None,
        )

    def get_session_detail(
        self,
        session_id: int,
    ) -> AdminSessionDetailRecord:
        detail = self.repository.get_session_detail(session_id)
        if detail is None:
            raise AdminValidationError("会话不存在")
        return detail

    def list_feedback(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AdminFeedbackRecord], int]:
        return self.repository.list_feedback(
            limit=limit,
            offset=offset,
        )

    def get_feedback_summary(self) -> dict[str, object]:
        records = self.repository.get_feedback_breakdown()
        total = sum(item.total for item in records)
        positive = sum(item.positive for item in records)
        negative = sum(item.negative for item in records)

        breakdown = [
            {
                "intent": item.intent,
                "total": item.total,
                "positive": item.positive,
                "negative": item.negative,
                "satisfaction_rate": self._rate(
                    item.positive,
                    item.total,
                ),
            }
            for item in records
        ]
        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "satisfaction_rate": self._rate(positive, total),
            "by_intent": breakdown,
        }

    def get_daily_question_trend(
        self,
        *,
        days: int,
        today: date | None = None,
    ) -> dict[str, object]:
        if days < 1 or days > 90:
            raise AdminValidationError("统计天数必须在 1 到 90 之间")

        end_date = today or date.today()
        start_date = end_date - timedelta(days=days - 1)
        rows = self.repository.list_daily_questions(
            start_date=start_date,
            end_date=end_date,
        )
        by_date = {
            item.usage_date: item.question_count
            for item in rows
        }
        points = []
        total = 0
        for index in range(days):
            current = start_date + timedelta(days=index)
            count = int(by_date.get(current, 0))
            total += count
            points.append(
                {
                    "date": current,
                    "question_count": count,
                }
            )

        return {
            "days": days,
            "total_questions": total,
            "average_per_day": round(total / days, 2),
            "items": points,
        }
