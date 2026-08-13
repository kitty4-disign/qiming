from __future__ import annotations

import time

import pytest

from deeptutor.education.models import EducationStage, StudentProfile
from deeptutor.education.recommender import (
    RecommendationContext,
    recommend,
    summarize_mastery,
)
from deeptutor.learning.models import (
    ErrorType,
    KnowledgePoint,
    KnowledgeType,
    LearningModule,
    LearningProgress,
    LearningStage,
    PendingQuestion,
    QuizAttempt,
    RepetitionState,
    ReviewTask,
)


def _make_profile(**overrides) -> StudentProfile:
    payload = {
        "display_name": "小航",
        "stage": EducationStage.PRIMARY_UPPER,
        "grade": 5,
        "textbook_id": "k12-ai-primary-upper",
        "interests": ["机器人"],
        "preferred_modalities": ["dialogue", "quiz"],
        "learning_goal": "理解图像识别",
    }
    payload.update(overrides)
    return StudentProfile(**payload)


def _make_progress(
    *,
    kp_names: list[str] = None,
    mastery_levels: dict[str, float] | None = None,
    current_kp_index: int = 0,
    quiz_attempts: list[QuizAttempt] | None = None,
    review_queue: list[ReviewTask] | None = None,
    pending_question: PendingQuestion | None = None,
) -> LearningProgress:
    if kp_names is None:
        kp_names = ["像素与数字图像", "图像特征", "训练集与测试集", "图像分类"]
    module_id = "m0"
    knowledge_points = [
        KnowledgePoint(
            id=f"m0_kp{i}",
            name=name,
            type=KnowledgeType.CONCEPT,
            module_id=module_id,
        )
        for i, name in enumerate(kp_names)
    ]
    progress = LearningProgress(
        book_id="edu_k12_ai_primary_upper_image_recognition",
        modules=[
            LearningModule(
                id=module_id,
                name="图像识别大冒险",
                order=0,
                knowledge_points=knowledge_points,
            )
        ],
        current_module_id=module_id,
        current_stage=LearningStage.EXPLAIN,
        current_kp_index=current_kp_index,
    )
    for kp_id, level in (mastery_levels or {}).items():
        progress.mastery_levels[kp_id] = level
        progress.knowledge_types[kp_id] = KnowledgeType.CONCEPT
    progress.quiz_attempts = quiz_attempts or []
    progress.review_queue = review_queue or []
    progress.pending_question = pending_question
    return progress


def _make_ctx(
    progress: LearningProgress,
    profile: StudentProfile | None = None,
    course_id: str = "image-recognition",
    course_title: str = "图像识别大冒险",
    recommended_actions: list[str] | None = None,
    now: float = 1000.0,
) -> RecommendationContext:
    return RecommendationContext(
        profile=profile or _make_profile(),
        course_id=course_id,
        course_title=course_title,
        knowledge_points=["像素与数字图像", "图像特征", "训练集与测试集", "图像分类"],
        recommended_actions=recommended_actions or ["dialogue", "animation", "storybook", "quiz"],
        mastery_path_id="edu_k12_ai_primary_upper_image_recognition",
        progress=progress,
        now=now,
    )


def test_pending_question_has_highest_priority():
    progress = _make_progress(
        pending_question=PendingQuestion(
            question_id="q1",
            knowledge_point_id="m0_kp1",
            module_id="m0",
            prompt="什么是像素？",
            expected_answer="像素是数字图像的最小单位",
        ),
    )
    ctx = _make_ctx(progress)
    rec = recommend(ctx)
    assert rec.reasons[0].code == "pending_question"
    assert rec.activity == "quiz"
    assert rec.knowledge_point_id == "m0_kp1"


def test_due_review_has_highest_priority_after_pending():
    progress = _make_progress(
        mastery_levels={"m0_kp0": 0.8, "m0_kp1": 0.0},
        review_queue=[
            ReviewTask(
                id="rt1",
                knowledge_point_id="m0_kp0",
                knowledge_type=KnowledgeType.CONCEPT,
                due_at=500.0,  # due in the past
                priority=5,
                state=RepetitionState(interval_index=1, next_review_at=500.0),
            )
        ],
    )
    ctx = _make_ctx(progress, now=1000.0)
    rec = recommend(ctx)
    assert rec.reasons[0].code == "due_review"
    assert rec.knowledge_point_id == "m0_kp0"


def test_wrong_answer_recommends_weak_point():
    progress = _make_progress(
        mastery_levels={"m0_kp0": 0.3},
        current_kp_index=0,
        quiz_attempts=[
            QuizAttempt(
                question_id="q1",
                knowledge_point_id="m0_kp0",
                module_id="m0",
                is_correct=False,
                error_type=ErrorType.UNDERSTANDING_DEVIATION,
            ),
        ],
    )
    ctx = _make_ctx(progress)
    rec = recommend(ctx)
    assert rec.reasons[0].code == "weak_point"
    assert rec.knowledge_point_id == "m0_kp0"
    assert rec.activity in ("lesson", "quiz")


def test_next_new_point_when_no_weakness():
    progress = _make_progress(
        mastery_levels={"m0_kp0": 0.8},
        current_kp_index=1,
    )
    ctx = _make_ctx(progress)
    rec = recommend(ctx)
    assert rec.reasons[0].code == "next_new_point"
    assert rec.knowledge_point_id == "m0_kp1"


def test_preferred_modality_breaks_tie_only():
    """Preference should influence the activity but not the priority order."""
    # With animation preferred first, the next_new_point should pick animation.
    progress = _make_progress(
        mastery_levels={"m0_kp0": 0.8},
        current_kp_index=1,
    )
    profile_animation = _make_profile(preferred_modalities=["animation", "quiz"])
    ctx = _make_ctx(progress, profile=profile_animation)
    rec = recommend(ctx)
    assert rec.reasons[0].code == "next_new_point"
    assert rec.activity == "animation"
    # Preference reason is added.
    assert any(r.code == "preference_match" for r in rec.reasons)


def test_recommendation_is_deterministic():
    progress = _make_progress(
        mastery_levels={"m0_kp0": 0.3},
        quiz_attempts=[
            QuizAttempt(
                question_id="q1",
                knowledge_point_id="m0_kp0",
                module_id="m0",
                is_correct=False,
                error_type=ErrorType.APPLICATION_ERROR,
            ),
        ],
    )
    ctx = _make_ctx(progress)
    rec1 = recommend(ctx)
    rec2 = recommend(ctx)
    assert rec1.model_dump_json() == rec2.model_dump_json()


def test_course_complete_recommendation():
    progress = _make_progress(
        mastery_levels={f"m0_kp{i}": 0.9 for i in range(4)},
    )
    ctx = _make_ctx(progress)
    rec = recommend(ctx)
    assert rec.reasons[0].code == "course_complete"


def test_primary_lower_blocks_coding():
    progress = _make_progress()
    profile = _make_profile(
        stage=EducationStage.PRIMARY_LOWER,
        grade=2,
        textbook_id="k12-ai-primary-lower",
        preferred_modalities=["coding", "quiz"],
    )
    ctx = _make_ctx(
        progress,
        profile=profile,
        course_id="smart-friends",
        recommended_actions=["dialogue", "storybook", "quiz"],
    )
    rec = recommend(ctx)
    # No pending, no review, no weak point → next_new_point with lesson (not coding).
    assert rec.activity != "coding"


def test_summarize_mastery_counts():
    progress = _make_progress(
        mastery_levels={"m0_kp0": 0.9, "m0_kp1": 0.5, "m0_kp2": 0.0},
    )
    summary = summarize_mastery(progress)
    assert summary == {"total": 4, "mastered": 1, "learning": 1, "new": 2}
