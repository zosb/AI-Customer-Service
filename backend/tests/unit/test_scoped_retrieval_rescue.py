from __future__ import annotations

import pytest

from app.services.chat.streaming_answer_service import (
    ChatStreamingAnswerService,
)


def test_scoped_rescue_threshold_keeps_global_threshold_intact() -> None:
    threshold = ChatStreamingAnswerService._scoped_rescue_threshold(
        normal_threshold=0.55,
        route_threshold=0.35,
    )

    assert threshold == pytest.approx(0.45)


def test_scoped_rescue_is_disabled_when_normal_threshold_is_already_lower() -> None:
    threshold = ChatStreamingAnswerService._scoped_rescue_threshold(
        normal_threshold=0.40,
        route_threshold=0.35,
    )

    assert threshold is None


def test_scoped_rescue_accepts_reliable_business_route() -> None:
    allowed = ChatStreamingAnswerService._can_attempt_scoped_rescue(
        intent="logistics",
        route_score=0.425,
        route_threshold=0.35,
    )

    assert allowed is True


def test_scoped_rescue_rejects_general_intent() -> None:
    allowed = ChatStreamingAnswerService._can_attempt_scoped_rescue(
        intent="general",
        route_score=0.90,
        route_threshold=0.35,
    )

    assert allowed is False


def test_scoped_rescue_rejects_weak_route_score() -> None:
    allowed = ChatStreamingAnswerService._can_attempt_scoped_rescue(
        intent="logistics",
        route_score=0.39,
        route_threshold=0.35,
    )

    assert allowed is False


def test_scoped_rescue_accepts_contextual_general_when_route_is_reliable() -> None:
    allowed = ChatStreamingAnswerService._can_attempt_scoped_rescue(
        intent="general",
        route_score=0.52,
        route_threshold=0.35,
        contextual_followup=True,
    )

    assert allowed is True


def test_scoped_rescue_still_rejects_non_contextual_general() -> None:
    allowed = ChatStreamingAnswerService._can_attempt_scoped_rescue(
        intent="general",
        route_score=0.90,
        route_threshold=0.35,
        contextual_followup=False,
    )

    assert allowed is False
