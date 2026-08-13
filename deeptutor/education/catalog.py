from __future__ import annotations

from functools import lru_cache
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field
import yaml

from deeptutor.education.models import EducationStage, StudentProfile


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title_zh: str
    title_en: str
    summary_zh: str
    summary_en: str = ""
    knowledge_points: list[str] = Field(min_length=1)
    recommended_actions: list[str] = Field(min_length=1)
    # Catalog v2 fields (M4 §9.2). All have defaults so v1 YAML stays valid.
    prerequisite_ids: list[str] = Field(default_factory=list)
    estimated_minutes: int = Field(default=20, ge=1, le=600)
    difficulty: int = Field(default=1, ge=1, le=5)
    age_policy: str = Field(default="", max_length=40)
    default_knowledge_point_id: str = Field(default="", max_length=80)
    resource_ids: list[str] = Field(default_factory=list)
    coding_task_ids: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list, max_length=10)
    common_misconceptions: list[str] = Field(default_factory=list, max_length=10)
    safety_notes: str = Field(default="", max_length=1000)
    reference_sources: list[str] = Field(default_factory=list, max_length=10)


class Textbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title_zh: str
    title_en: str
    stage: EducationStage
    knowledge_base: str
    default_course_id: str
    courses: list[Course] = Field(min_length=1)


class CurriculumCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    textbooks: list[Textbook] = Field(min_length=4)


@lru_cache(maxsize=1)
def load_catalog() -> CurriculumCatalog:
    raw = resources.files(__package__).joinpath("catalog.yaml").read_text(encoding="utf-8")
    return CurriculumCatalog.model_validate(yaml.safe_load(raw))


def resolve_curriculum(profile: StudentProfile) -> Textbook:
    textbook = next(
        (item for item in load_catalog().textbooks if item.id == profile.textbook_id), None
    )
    if textbook is None:
        raise ValueError(f"Unknown textbook: {profile.textbook_id}")
    if textbook.stage != profile.stage:
        raise ValueError(
            f"Textbook {profile.textbook_id} does not belong to stage {profile.stage.value}"
        )
    return textbook


def resolve_visible_knowledge_bases(
    profile: StudentProfile, *, visible_names: set[str]
) -> tuple[list[str], list[str]]:
    textbook = resolve_curriculum(profile)
    if textbook.knowledge_base in visible_names:
        return [textbook.knowledge_base], []
    return [], [f"knowledge_base_not_ready:{textbook.knowledge_base}"]
