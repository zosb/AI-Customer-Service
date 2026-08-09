from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.repositories.chat_repository import ChatRepository


@dataclass
class FakeResult:
    row: dict[str, Any] | None = None
    scalar: Any = None

    def mappings(self) -> "FakeResult":
        return self

    def first(self):
        return self.row

    def scalar_one_or_none(self):
        return self.scalar


class FakeDatabase:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def execute(self, statement, parameters=None):
        self.calls.append((str(statement), parameters))
        if self.results:
            return self.results.pop(0)
        return FakeResult()


def test_daily_quota_first_question_inserts_usage_row():
    database = FakeDatabase([
        FakeResult(row=None),
        FakeResult(),
    ])
    repository = ChatRepository(database)  # type: ignore[arg-type]

    count = repository.try_consume_daily_question(
        user_id=7,
        daily_limit=100,
    )

    assert count == 1
    assert len(database.calls) == 2
    assert "FROM daily_question_usage" in database.calls[0][0]
    assert "INSERT INTO daily_question_usage" in database.calls[1][0]


def test_daily_quota_existing_row_is_incremented():
    database = FakeDatabase([
        FakeResult(row={"question_count": 2}),
        FakeResult(),
    ])
    repository = ChatRepository(database)  # type: ignore[arg-type]

    count = repository.try_consume_daily_question(
        user_id=7,
        daily_limit=100,
    )

    assert count == 3
    assert "UPDATE daily_question_usage" in database.calls[1][0]
    assert database.calls[1][1] == {
        "user_id": 7,
        "question_count": 3,
    }


def test_daily_quota_at_limit_returns_none_without_update():
    database = FakeDatabase([
        FakeResult(row={"question_count": 100}),
    ])
    repository = ChatRepository(database)  # type: ignore[arg-type]

    count = repository.try_consume_daily_question(
        user_id=7,
        daily_limit=100,
    )

    assert count is None
    assert len(database.calls) == 1


def test_daily_quota_rejects_invalid_limit():
    repository = ChatRepository(FakeDatabase([]))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="daily_limit"):
        repository.try_consume_daily_question(
            user_id=7,
            daily_limit=0,
        )


def test_get_today_question_count_uses_business_table():
    database = FakeDatabase([
        FakeResult(scalar=9),
    ])
    repository = ChatRepository(database)  # type: ignore[arg-type]

    count = repository.get_today_question_count(user_id=7)

    assert count == 9
    assert "FROM daily_question_usage" in database.calls[0][0]
