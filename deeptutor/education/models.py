from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EducationStage(str, Enum):
    PRIMARY_LOWER = "primary_lower"
    PRIMARY_UPPER = "primary_upper"
    MIDDLE = "middle"
    HIGH = "high"


STAGE_GRADE_RANGE: dict[EducationStage, tuple[int, int]] = {
    EducationStage.PRIMARY_LOWER: (1, 3),
    EducationStage.PRIMARY_UPPER: (4, 6),
    EducationStage.MIDDLE: (7, 9),
    EducationStage.HIGH: (10, 12),
}

LearningModality = Literal["dialogue", "animation", "storybook", "coding", "quiz"]


class StudentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: int = 1
    display_name: str = Field(default="同学", min_length=1, max_length=30)
    stage: EducationStage
    grade: int = Field(ge=1, le=12)
    textbook_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    interests: list[str] = Field(default_factory=list, max_length=5)
    preferred_modalities: list[LearningModality] = Field(
        default_factory=lambda: ["dialogue", "quiz"], max_length=5
    )
    learning_goal: str = Field(default="", max_length=200)

    @field_validator("interests")
    @classmethod
    def normalize_interests(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        for raw in value:
            item = str(raw).strip()[:30]
            if item and item not in result:
                result.append(item)
        return result

    @field_validator("preferred_modalities")
    @classmethod
    def dedupe_modalities(cls, value: list[LearningModality]) -> list[LearningModality]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_stage_grade(self) -> "StudentProfile":
        low, high = STAGE_GRADE_RANGE[self.stage]
        if not low <= self.grade <= high:
            raise ValueError(f"grade must be between {low} and {high} for {self.stage.value}")
        return self
