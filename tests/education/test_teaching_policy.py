import pytest

from deeptutor.education.models import StudentProfile
from deeptutor.education.teaching_policy import decide_teaching
from deeptutor.learning.models import (
    KnowledgePoint,
    KnowledgeType,
    LearningModule,
    LearningProgress,
)


def progress_for(kp_type: KnowledgeType = KnowledgeType.PROCEDURE) -> LearningProgress:
    kp = KnowledgePoint(id="kp", name="训练集与测试集", type=kp_type, module_id="m")
    return LearningProgress(
        book_id="path",
        modules=[LearningModule(id="m", name="module", order=0, knowledge_points=[kp])],
    )


@pytest.mark.parametrize(
    ("stage", "grade", "expected_difficulty", "expected_count"),
    [
        ("primary_lower", 2, 1, 2),
        ("primary_upper", 5, 2, 3),
        ("middle", 8, 3, 4),
        ("high", 11, 4, 5),
    ],
)
def test_stage_changes_teaching_decision(stage, grade, expected_difficulty, expected_count):
    decision = decide_teaching(
        profile=StudentProfile(
            stage=stage,
            grade=grade,
            textbook_id=f"book-{stage.replace('_', '-')}",
            preferred_modalities=[],
        ),
        progress=progress_for(),
        allowed_modalities=["dialogue", "animation", "storybook", "coding", "quiz"],
    )
    assert decision.difficulty == expected_difficulty
    assert decision.question_count == expected_count


def test_misconception_changes_activity_and_reason():
    decision = decide_teaching(
        profile=StudentProfile(
            stage="middle",
            grade=8,
            textbook_id="book-middle",
            preferred_modalities=["dialogue"],
        ),
        progress=progress_for(),
        allowed_modalities=["dialogue", "animation", "quiz"],
        misconceptions=["测试集参与训练"],
    )
    assert decision.activity == "animation"
    assert "REPEATED_MISCONCEPTION" in decision.reason_codes


def test_primary_lower_never_selects_code():
    decision = decide_teaching(
        profile=StudentProfile(
            stage="primary_lower",
            grade=2,
            textbook_id="book-primary-lower",
            preferred_modalities=["coding"],
        ),
        progress=progress_for(),
        allowed_modalities=["coding", "dialogue"],
    )
    assert decision.activity == "lesson"
    assert decision.use_code is False
