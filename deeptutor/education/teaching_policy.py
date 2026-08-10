from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from deeptutor.education.activity_models import EducationActivity
from deeptutor.education.models import EducationStage, LearningModality, StudentProfile
from deeptutor.learning.models import LearningProgress
from deeptutor.learning.policy import next_objective

TeachingReasonCode = str

_ACTIVITY_BY_MODALITY: dict[LearningModality, EducationActivity] = {
    "dialogue": "lesson",
    "animation": "animation",
    "storybook": "storybook",
    "coding": "coding",
    "quiz": "quiz",
}

_STAGE_DEFAULTS = {
    EducationStage.PRIMARY_LOWER: ("storybook", 1, 2, "high", False, True),
    EducationStage.PRIMARY_UPPER: ("animation", 2, 3, "medium_high", False, True),
    EducationStage.MIDDLE: ("animation", 3, 4, "medium", False, True),
    EducationStage.HIGH: ("coding", 4, 5, "low", True, False),
}


class TeachingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = "fp1"
    activity: EducationActivity
    difficulty: int = Field(ge=1, le=4)
    explanation_depth: int = Field(ge=1, le=4)
    question_count: int = Field(ge=1, le=10)
    hint_level: str
    use_code: bool
    use_visualization: bool
    knowledge_point_id: str = ""
    reason_codes: list[TeachingReasonCode] = Field(default_factory=list)


def decide_teaching(
    *,
    profile: StudentProfile,
    progress: LearningProgress,
    allowed_modalities: list[str],
    misconceptions: list[str] | None = None,
) -> TeachingDecision:
    """Choose pedagogy deterministically; mastery ordering remains authoritative."""
    step = next_objective(progress)
    default, difficulty, count, hint, use_code, use_visualization = _STAGE_DEFAULTS[profile.stage]
    allowed = [_ACTIVITY_BY_MODALITY[item] for item in allowed_modalities if item in _ACTIVITY_BY_MODALITY]
    if "lesson" not in allowed:
        allowed.insert(0, "lesson")

    reasons = [f"STAGE_{profile.stage.value.upper()}"]
    activity: EducationActivity = default
    if step.action in {"answer_pending", "review"}:
        activity = "quiz"
        reasons.append("DUE_ASSESSMENT")
    elif misconceptions:
        activity = "animation" if "animation" in allowed else "lesson"
        hint = "high" if profile.stage == EducationStage.PRIMARY_LOWER else "medium_high"
        reasons.append("REPEATED_MISCONCEPTION")
    else:
        for modality in profile.preferred_modalities:
            preferred = _ACTIVITY_BY_MODALITY[modality]
            if preferred in allowed and not (
                profile.stage == EducationStage.PRIMARY_LOWER and preferred == "coding"
            ):
                activity = preferred
                reasons.append(f"PREFERS_{modality.upper()}")
                break
    if activity not in allowed or (profile.stage == EducationStage.PRIMARY_LOWER and activity == "coding"):
        activity = "lesson"
    if step.status == "learning":
        reasons.append("LOW_MASTERY")

    return TeachingDecision(
        activity=activity,
        difficulty=difficulty,
        explanation_depth=difficulty,
        question_count=count,
        hint_level=hint,
        use_code=use_code and "coding" in allowed,
        use_visualization=use_visualization and "animation" in allowed,
        knowledge_point_id=step.knowledge_point_id,
        reason_codes=list(dict.fromkeys(reasons)),
    )


__all__ = ["TeachingDecision", "decide_teaching"]
