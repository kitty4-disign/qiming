from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EducationActivity = Literal["lesson", "quiz", "animation", "storybook", "coding", "resource"]

ActivityEventType = Literal["launched", "completed", "abandoned"]

RecommendationReasonCode = Literal[
    "pending_question",
    "due_review",
    "weak_point",
    "next_new_point",
    "preference_match",
    "course_complete",
]


class LearningEvent(BaseModel):
    """A single learning activity event for the current user.

    Persists only the minimum evidence required to explain recommendations and
    derive healthy gamification.  No dialogue content, names, contact info or
    API keys are stored.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=80)
    course_id: str = Field(min_length=1, max_length=80)
    mastery_path_id: str = Field(min_length=1, max_length=120)
    activity: EducationActivity
    event_type: ActivityEventType
    knowledge_point_id: str = Field(default="", max_length=120)
    episode_id: str = Field(default="", max_length=80)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    duration_seconds: int | None = Field(default=None, ge=0, le=24 * 3600)
    idempotency_key: str = Field(default="", max_length=120)
    created_at: float = Field(default_factory=time.time)


class RecommendationReason(BaseModel):
    """A human-readable, machine-checkable reason for a recommendation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: RecommendationReasonCode
    message_zh: str = Field(min_length=1, max_length=200)
    evidence: dict[str, str | int | float] = Field(default_factory=dict)


class EducationRecommendation(BaseModel):
    """The next step the workspace should surface to the learner."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_id: str = Field(min_length=1, max_length=80)
    knowledge_point_id: str = Field(default="", max_length=120)
    knowledge_point_name: str = Field(default="", max_length=200)
    activity: EducationActivity
    title: str = Field(min_length=1, max_length=120)
    reasons: list[RecommendationReason] = Field(default_factory=list, max_length=6)


class ActivityCompletion(BaseModel):
    """Payload accepted by ``POST /api/v1/education/events``.

    Only ``quiz`` or explicit mastery assess/grade may change mastery state;
    other activities merely record learning evidence.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_id: str = Field(min_length=1, max_length=80)
    mastery_path_id: str = Field(min_length=1, max_length=120)
    activity: EducationActivity
    event_type: ActivityEventType
    knowledge_point_id: str = Field(default="", max_length=120)
    episode_id: str = Field(default="", max_length=80)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    duration_seconds: int | None = Field(default=None, ge=0, le=24 * 3600)
    idempotency_key: str = Field(min_length=1, max_length=120)


__all__ = [
    "ActivityCompletion",
    "ActivityEventType",
    "EducationActivity",
    "EducationRecommendation",
    "LearningEvent",
    "RecommendationReason",
    "RecommendationReasonCode",
]
