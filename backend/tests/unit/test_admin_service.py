from __future__ import annotations

from datetime import date, datetime

import pytest

from app.repositories.admin_repository import (
    AdminFeedbackBreakdownRecord,
    AdminOverviewRecord,
    DailyQuestionRecord,
)
from app.services.admin.service import AdminService, AdminValidationError


class FakeRepository:
    def get_overview(self, *, today):
        assert today == date(2026, 8, 7)
        return AdminOverviewRecord(
            total_users=10,
            active_users=9,
            total_sessions=20,
            active_sessions=7,
            total_messages=80,
            today_questions=12,
            total_knowledge_bases=3,
            total_documents=8,
            feedback_total=4,
            positive_feedback=3,
            negative_feedback=1,
            prompt_token_estimate=1200,
            completion_token_count=600,
        )

    def get_feedback_breakdown(self):
        return [
            AdminFeedbackBreakdownRecord(
                intent="refund",
                total=3,
                positive=2,
                negative=1,
            ),
            AdminFeedbackBreakdownRecord(
                intent="logistics",
                total=1,
                positive=1,
                negative=0,
            ),
        ]

    def list_daily_questions(self, *, start_date, end_date):
        assert start_date == date(2026, 8, 5)
        assert end_date == date(2026, 8, 7)
        return [
            DailyQuestionRecord(date(2026, 8, 5), 2),
            DailyQuestionRecord(date(2026, 8, 7), 4),
        ]


def test_overview_calculates_satisfaction_rate():
    result = AdminService(FakeRepository()).get_overview(
        today=date(2026, 8, 7)
    )
    assert result["today_questions"] == 12
    assert result["satisfaction_rate"] == 75.0


def test_feedback_summary_groups_intents_and_rate():
    result = AdminService(FakeRepository()).get_feedback_summary()
    assert result["total"] == 4
    assert result["positive"] == 3
    assert result["satisfaction_rate"] == 75.0
    assert result["by_intent"][0]["intent"] == "refund"
    assert result["by_intent"][0]["satisfaction_rate"] == 66.67


def test_daily_trend_zero_fills_missing_dates():
    result = AdminService(FakeRepository()).get_daily_question_trend(
        days=3,
        today=date(2026, 8, 7),
    )
    assert [item["question_count"] for item in result["items"]] == [2, 0, 4]
    assert result["total_questions"] == 6
    assert result["average_per_day"] == 2.0


def test_daily_trend_rejects_invalid_days():
    with pytest.raises(AdminValidationError):
        AdminService(FakeRepository()).get_daily_question_trend(days=0)
