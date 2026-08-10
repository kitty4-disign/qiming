from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeptutor.education.activity_models import EducationActivity
from deeptutor.education.models import EducationStage

EpisodeStatus = Literal["active", "completed", "abandoned"]


class LearningEpisode(BaseModel):
    """A compact, inspectable record of one measurable learning cycle."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: int = 1
    episode_id: str = Field(min_length=1, max_length=80)
    course_id: str = Field(min_length=1, max_length=80)
    mastery_path_id: str = Field(min_length=1, max_length=120)
    knowledge_point_id: str = Field(min_length=1, max_length=120)
    knowledge_point_name: str = Field(default="", max_length=200)
    stage: EducationStage
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None
    pre_score: float = Field(ge=0, le=100)
    post_score: float | None = Field(default=None, ge=0, le=100)
    initial_misconceptions: list[str] = Field(default_factory=list, max_length=20)
    resolved_misconceptions: list[str] = Field(default_factory=list, max_length=20)
    activities_used: list[EducationActivity] = Field(default_factory=list, max_length=20)
    activity_reasons: list[str] = Field(default_factory=list, max_length=20)
    mastery_before: float = Field(default=0, ge=0, le=1)
    mastery_after: float | None = Field(default=None, ge=0, le=1)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    status: EpisodeStatus = "active"

    @field_validator(
        "initial_misconceptions",
        "resolved_misconceptions",
        "activity_reasons",
        "source_ids",
    )
    @classmethod
    def dedupe_text(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @field_validator("activities_used")
    @classmethod
    def dedupe_activities(cls, value: list[EducationActivity]) -> list[EducationActivity]:
        return list(dict.fromkeys(value))

    @property
    def raw_gain(self) -> float | None:
        return None if self.post_score is None else self.post_score - self.pre_score

    @property
    def normalized_gain(self) -> float | None:
        if self.post_score is None:
            return None
        return (self.post_score - self.pre_score) / max(1.0, 100.0 - self.pre_score)

    def evidence_dump(self) -> dict:
        data = self.model_dump(mode="json")
        data["raw_gain"] = self.raw_gain
        data["normalized_gain"] = self.normalized_gain
        return data


class CreateEpisodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_id: str = Field(min_length=1, max_length=80)
    knowledge_point_id: str = Field(min_length=1, max_length=120)
    pre_score: float = Field(ge=0, le=100)
    initial_misconceptions: list[str] = Field(default_factory=list, max_length=20)


class CompleteEpisodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    post_score: float = Field(ge=0, le=100)
    resolved_misconceptions: list[str] = Field(default_factory=list, max_length=20)
    activities_used: list[EducationActivity] = Field(default_factory=list, max_length=20)
    activity_reasons: list[str] = Field(default_factory=list, max_length=20)
    source_ids: list[str] = Field(default_factory=list, max_length=20)


__all__ = [
    "CompleteEpisodeRequest",
    "CreateEpisodeRequest",
    "EpisodeStatus",
    "LearningEpisode",
]
