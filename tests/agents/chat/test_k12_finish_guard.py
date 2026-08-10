from __future__ import annotations

import json

from deeptutor.agents.chat.k12_finish_guard import k12_finish_is_allowed
from deeptutor.core.context import UnifiedContext


def _context(*, mode: str = "lesson", limit_reached: bool = False) -> UnifiedContext:
    return UnifiedContext(
        metadata={
            "ask_user_turn_boundary": True,
            "education_activity_mode": mode,
            "education_quiz_limit_reached": limit_reached,
        }
    )


def _tool_message(payload: dict) -> dict[str, str]:
    return {"role": "tool", "content": json.dumps(payload)}


def test_non_k12_or_unmanaged_mastery_finish_is_unchanged() -> None:
    assert k12_finish_is_allowed(UnifiedContext(), []) is True
    assert (
        k12_finish_is_allowed(
            UnifiedContext(metadata={"ask_user_turn_boundary": True}),
            [],
        )
        is True
    )


def test_incomplete_lesson_cannot_finish_without_ask_user() -> None:
    messages = [
        _tool_message(
            {
                "status": "active",
                "next": {"action": "teach", "knowledge_point_id": "kp-1"},
            }
        )
    ]

    assert k12_finish_is_allowed(_context(mode="lesson"), messages) is False


def test_completed_mastery_path_may_finish_normally() -> None:
    messages = [
        _tool_message(
            {
                "status": "active",
                "next": {"action": "complete", "knowledge_point_id": ""},
            }
        )
    ]

    assert k12_finish_is_allowed(_context(mode="lesson"), messages) is True


def test_final_quiz_requires_real_grade_before_summary_finish() -> None:
    status_only = [
        _tool_message(
            {
                "status": "active",
                "next": {"action": "answer_pending", "knowledge_point_id": "kp-1"},
            }
        )
    ]
    graded = status_only + [
        _tool_message(
            {
                "is_correct": True,
                "knowledge_point_id": "kp-1",
                "mastery": 0.9,
                "next": {"action": "teach", "knowledge_point_id": "kp-2"},
            }
        )
    ]

    context = _context(mode="quiz", limit_reached=True)
    assert k12_finish_is_allowed(context, status_only) is False
    assert k12_finish_is_allowed(context, graded) is True
