from __future__ import annotations

import pytest

from deeptutor.app import EducationContext, TurnRequest
from deeptutor.runtime.request_contracts import (
    validate_education_request_context,
    validate_k12_tutor_request_config,
)


def test_k12_config_contains_only_capability_parameters() -> None:
    model = validate_k12_tutor_request_config(
        {
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
            "activity_mode": "quiz",
        }
    )

    assert model.activity_mode == "quiz"


@pytest.mark.parametrize("field", ["stage", "grade", "knowledge_point_id"])
def test_k12_config_rejects_teaching_context_fields(field: str) -> None:
    raw = {
        "course_id": "image-recognition",
        "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
        field: "primary_upper" if field == "stage" else 5,
    }
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        validate_k12_tutor_request_config(raw)


def test_education_context_validates_stage_grade_and_target() -> None:
    assert validate_education_request_context(
        {
            "stage": "primary_upper",
            "grade": 5,
            "knowledge_point_id": "path_m0_kp0",
        }
    ) == {
        "stage": "primary_upper",
        "grade": 5,
        "knowledge_point_id": "path_m0_kp0",
    }


def test_education_context_rejects_stage_grade_mismatch() -> None:
    with pytest.raises(ValueError, match="grade must be between 4 and 6"):
        validate_education_request_context({"stage": "primary_upper", "grade": 8})


def test_education_context_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        validate_education_request_context(
            {"stage": "primary_upper", "grade": 5, "unexpected": True}
        )


def test_sdk_turn_request_serializes_public_education_context() -> None:
    payload = TurnRequest(
        content="start lesson",
        capability="k12_tutor",
        education_context=EducationContext(
            stage="primary_upper", grade=5, knowledge_point_id="path_m0_kp0"
        ),
    ).to_payload()

    assert payload["education_context"] == {
        "stage": "primary_upper",
        "grade": 5,
        "knowledge_point_id": "path_m0_kp0",
    }
