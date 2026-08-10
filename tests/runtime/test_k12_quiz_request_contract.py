from __future__ import annotations

import pytest

from deeptutor.runtime.request_contracts import validate_capability_config


def test_k12_quiz_state_round_trips_through_public_contract() -> None:
    config = validate_capability_config(
        "k12_tutor",
        {
            "course_id": "course-1",
            "mastery_path_id": "path_1",
            "activity_mode": "quiz",
            "quiz_run_id": "1723296000000",
            "quiz_question_count": 3,
            "quiz_answered_count": 2,
            "quiz_last_answered_turn_id": "turn-2",
        },
    )

    assert config["activity_mode"] == "quiz"
    assert config["quiz_question_count"] == 3
    assert config["quiz_answered_count"] == 2
    assert config["quiz_last_answered_turn_id"] == "turn-2"


def test_k12_quiz_contract_rejects_answer_count_above_limit() -> None:
    with pytest.raises(ValueError, match="quiz_answered_count"):
        validate_capability_config(
            "k12_tutor",
            {
                "course_id": "course-1",
                "mastery_path_id": "path_1",
                "activity_mode": "quiz",
                "quiz_question_count": 3,
                "quiz_answered_count": 4,
            },
        )
