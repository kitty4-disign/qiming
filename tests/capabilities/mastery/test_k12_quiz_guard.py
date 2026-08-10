from __future__ import annotations

import pytest

from deeptutor.capabilities.mastery import MasteryLoopCapability
from deeptutor.capabilities.mastery.tools import MasteryQuizTool
from deeptutor.core.context import UnifiedContext


def test_mastery_loop_injects_private_quiz_limit_for_final_k12_turn() -> None:
    context = UnifiedContext(
        session_id="session-1",
        metadata={
            "mastery_mode": True,
            "mastery_path_id": "path-1",
            "turn_id": "turn-3",
            "education_quiz_question_count": 3,
            "education_quiz_answered_count": 3,
            "education_quiz_limit_reached": True,
        },
    )

    kwargs = MasteryLoopCapability().augment_kwargs(
        "mastery_quiz",
        {"knowledge_point_id": "kp-1"},
        context,
    )

    assert kwargs["_quiz_question_limit_reached"] is True
    assert kwargs["_quiz_question_count"] == 3
    assert kwargs["_mastery_path_id"] == "path-1"


@pytest.mark.asyncio
async def test_mastery_quiz_tool_refuses_question_after_limit() -> None:
    result = await MasteryQuizTool().execute(
        knowledge_point_id="kp-1",
        question="This must never be persisted",
        expected_answer="A",
        _mastery_path_id="path-1",
        _quiz_question_limit_reached=True,
        _quiz_question_count=3,
    )

    assert result.success is False
    assert "question limit reached" in result.content.lower()
    assert result.metadata["mastery_quiz"]["status"] == "question_limit_reached"
    assert result.metadata["mastery_quiz"]["question_count"] == 3
