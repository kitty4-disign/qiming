from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping

from deeptutor.education.activity_models import (
    EducationActivity,
    EducationRecommendation,
    RecommendationReason,
)
from deeptutor.education.models import EducationStage, LearningModality, StudentProfile
from deeptutor.learning.models import LearningProgress
from deeptutor.learning.policy import due_reviews

# Mastery below this threshold combined with recent wrong answers triggers a
# weak-point recommendation.
_WEAK_POINT_THRESHOLD = 0.6
# Recommendation progress remains a coarse dashboard signal; the authoritative
# TeachingPolicy uses the per-type mastery gates in ``deeptutor.learning.policy``.
_MASTERY_THRESHOLD = 0.7

# Map the frontend launch modalities to EducationActivity values.  ``dialogue``
# is the conversational lesson entry, which maps to ``lesson``.
_MODALITY_TO_ACTIVITY: dict[LearningModality, EducationActivity] = {
    "dialogue": "lesson",
    "animation": "animation",
    "storybook": "storybook",
    "coding": "coding",
    "quiz": "quiz",
}

# Stages that should not be offered coding activities by default.
_NO_CODING_STAGES = {EducationStage.PRIMARY_LOWER}


@dataclass
class RecommendationContext:
    """Inputs the deterministic recommender needs — all from existing data."""

    profile: StudentProfile
    course_id: str
    course_title: str
    knowledge_points: list[str]  # ordered display names from the catalog
    recommended_actions: list[str]  # LearningModality values allowed for this course
    mastery_path_id: str
    progress: LearningProgress
    now: float = 0.0

    def __post_init__(self) -> None:
        if not self.now:
            self.now = time.time()


def _kp_id_for_index(progress: LearningProgress, index: int) -> str:
    """Return the knowledge point id at ``index`` within the current module."""
    for module in progress.modules:
        if 0 <= index < len(module.knowledge_points):
            return module.knowledge_points[index].id
    return ""


def _kp_name(progress: LearningProgress, kp_id: str) -> str:
    for module in progress.modules:
        for kp in module.knowledge_points:
            if kp.id == kp_id:
                return kp.name
    return kp_id


def _current_kp_id(progress: LearningProgress) -> str:
    if not progress.modules:
        return ""
    return _kp_id_for_index(progress, progress.current_kp_index)


def _find_next_unlearned_kp(progress: LearningProgress) -> str:
    """First KP below the dashboard recommendation threshold."""
    for module in progress.modules:
        for kp in module.knowledge_points:
            if progress.mastery_levels.get(kp.id, 0.0) < _MASTERY_THRESHOLD:
                return kp.id
    return ""


def _has_recent_wrong(progress: LearningProgress, kp_id: str) -> bool:
    attempts = [a for a in progress.quiz_attempts if a.knowledge_point_id == kp_id]
    if not attempts:
        return False
    return not attempts[-1].is_correct


def _due_review_kp(progress: LearningProgress, now: float) -> str:
    """Return the highest-priority due review KP id, or empty."""
    due = due_reviews(progress, now=now)
    if not due:
        return ""
    return due[0].knowledge_point_id


def _select_activity(
    ctx: RecommendationContext,
    *,
    preferred: EducationActivity,
    fallback: EducationActivity,
) -> EducationActivity:
    """Choose an activity that satisfies teaching needs and stage safety."""
    allowed = _allowed_activities(ctx)
    if preferred in allowed:
        return preferred
    if fallback in allowed:
        return fallback
    # Stable fallback: lesson is always safe.
    return "lesson" if "lesson" in allowed else allowed[0]


def _allowed_activities(ctx: RecommendationContext) -> list[EducationActivity]:
    """Activities permitted for this course + stage, ordered by preference."""
    course_actions: list[EducationActivity] = []
    for action in ctx.recommended_actions:
        activity = _MODALITY_TO_ACTIVITY.get(action)  # type: ignore[arg-type]
        if activity and activity not in course_actions:
            course_actions.append(activity)
    # Always allow lesson as a safe default.
    if "lesson" not in course_actions:
        course_actions.insert(0, "lesson")

    # Stage safety: primary lower should not get coding.
    if ctx.profile.stage in _NO_CODING_STAGES and "coding" in course_actions:
        course_actions = [a for a in course_actions if a != "coding"]

    # Reorder by preferred_modalities (stable, preserves original order otherwise).
    preference_order: list[EducationActivity] = []
    for modality in ctx.profile.preferred_modalities:
        activity = _MODALITY_TO_ACTIVITY.get(modality)
        if activity and activity in course_actions and activity not in preference_order:
            preference_order.append(activity)
    for activity in course_actions:
        if activity not in preference_order:
            preference_order.append(activity)
    return preference_order


def recommend(ctx: RecommendationContext) -> EducationRecommendation:
    """Deterministic next-step recommendation.

    Priority order (fixed, no LLM, no random):
      1. pending_question → continue quiz
      2. due_review → review quiz
      3. weak_point (mastery < threshold + recent wrong) → targeted lesson/quiz
      4. next_new_point → lesson
      5. course_complete → coding / project
    """
    progress = ctx.progress
    allowed = _allowed_activities(ctx)

    # 1. Pending question — continue the current quiz.
    if progress.pending_question is not None:
        kp_id = progress.pending_question.knowledge_point_id
        return EducationRecommendation(
            course_id=ctx.course_id,
            knowledge_point_id=kp_id,
            knowledge_point_name=_kp_name(progress, kp_id),
            activity="quiz",
            title="继续回答上一道题",
            reasons=[
                RecommendationReason(
                    code="pending_question",
                    message_zh="你上一道题还没作答，先完成它再学新内容。",
                    evidence={"knowledge_point_id": kp_id},
                )
            ],
        )

    # 2. Due spaced review.
    due_kp = _due_review_kp(progress, ctx.now)
    if due_kp:
        activity = _select_activity(ctx, preferred="quiz", fallback="lesson")
        return EducationRecommendation(
            course_id=ctx.course_id,
            knowledge_point_id=due_kp,
            knowledge_point_name=_kp_name(progress, due_kp),
            activity=activity,
            title="复习到期知识点",
            reasons=[
                RecommendationReason(
                    code="due_review",
                    message_zh="这个知识点到了复习时间，练一练记得更牢。",
                    evidence={
                        "knowledge_point_id": due_kp,
                        "current_mastery": progress.mastery_levels.get(due_kp, 0.0),
                    },
                )
            ],
        )

    # 3. Weak point — mastery below threshold and recently wrong.
    current_kp = _current_kp_id(progress)
    if current_kp:
        mastery = progress.mastery_levels.get(current_kp, 0.0)
        if mastery < _WEAK_POINT_THRESHOLD and _has_recent_wrong(progress, current_kp):
            activity = _select_activity(ctx, preferred="lesson", fallback="quiz")
            return EducationRecommendation(
                course_id=ctx.course_id,
                knowledge_point_id=current_kp,
                knowledge_point_name=_kp_name(progress, current_kp),
                activity=activity,
                title="针对性练习薄弱知识点",
                reasons=[
                    RecommendationReason(
                        code="weak_point",
                        message_zh="你最近在这道题上答错了，先巩固一下再继续。",
                        evidence={
                            "knowledge_point_id": current_kp,
                            "current_mastery": mastery,
                            "threshold": _WEAK_POINT_THRESHOLD,
                        },
                    )
                ],
            )

    # 4. Next unlearned knowledge point.
    next_kp = _find_next_unlearned_kp(progress)
    if next_kp:
        preferred_modality = (
            _MODALITY_TO_ACTIVITY.get(ctx.profile.preferred_modalities[0])
            if ctx.profile.preferred_modalities
            else "lesson"
        )
        activity = _select_activity(
            ctx, preferred=preferred_modality or "lesson", fallback="lesson"
        )
        reason_code = "next_new_point"
        message = "接下来学习新的知识点。"
        evidence: dict[str, str | int | float] = {
            "knowledge_point_id": next_kp,
            "index": progress.current_kp_index,
        }
        # If the chosen activity came from a preference, add a preference reason.
        reasons = [
            RecommendationReason(
                code=reason_code,
                message_zh=message,
                evidence=evidence,
            )
        ]
        if (
            ctx.profile.preferred_modalities
            and _MODALITY_TO_ACTIVITY.get(ctx.profile.preferred_modalities[0]) == activity
        ):
            reasons.append(
                RecommendationReason(
                    code="preference_match",
                    message_zh="学习形式按你选择的偏好安排。",
                    evidence={"preferred_modality": ctx.profile.preferred_modalities[0]},
                )
            )
        return EducationRecommendation(
            course_id=ctx.course_id,
            knowledge_point_id=next_kp,
            knowledge_point_name=_kp_name(progress, next_kp),
            activity=activity,
            title="学习下一个知识点",
            reasons=reasons,
        )

    # 5. All mastered — recommend project / coding.
    activity = _select_activity(ctx, preferred="coding", fallback="lesson")
    return EducationRecommendation(
        course_id=ctx.course_id,
        knowledge_point_id="",
        knowledge_point_name="",
        activity=activity,
        title="全部掌握，尝试拓展创作",
        reasons=[
            RecommendationReason(
                code="course_complete",
                message_zh="当前课程的知识点已全部掌握，可以尝试项目式拓展。",
                evidence={
                    "mastered_count": sum(
                        1
                        for level in progress.mastery_levels.values()
                        if level >= _MASTERY_THRESHOLD
                    ),
                    "total_kps": len(
                        [kp for m in progress.modules for kp in m.knowledge_points]
                    ),
                },
            )
        ],
    )


def summarize_mastery(progress: LearningProgress) -> dict[str, int | float]:
    """Compact mastery counts for the dashboard.

    A knowledge point counts as "learning" (not "new") once the student has
    produced any evidence for it — a quiz attempt or a non-zero mastery level —
    even if every attempt was wrong (mastery 0.0). This prevents a fully-wrong
    KP from being mislabelled as untouched.
    """
    kp_ids = [kp.id for m in progress.modules for kp in m.knowledge_points]
    attempted_kp_ids = {a.knowledge_point_id for a in progress.quiz_attempts}
    mastered = 0
    learning = 0
    for kp_id in kp_ids:
        level = progress.mastery_levels.get(kp_id, 0.0)
        if level >= _MASTERY_THRESHOLD:
            mastered += 1
        elif kp_id in attempted_kp_ids or level > 0.0:
            learning += 1
    return {
        "total": len(kp_ids),
        "mastered": mastered,
        "learning": learning,
        "new": len(kp_ids) - mastered - learning,
    }


__all__ = [
    "RecommendationContext",
    "recommend",
    "summarize_mastery",
]
