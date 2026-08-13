from __future__ import annotations

from deeptutor.education.catalog import Course
from deeptutor.education.path_ids import build_mastery_path_id
from deeptutor.learning.models import (
    KnowledgePoint,
    KnowledgeType,
    LearningModule,
    LearningProgress,
)
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore


def _default_knowledge_type(name: str) -> KnowledgeType:
    lowered = name.lower()
    if any(
        token in name
        for token in ("安全", "伦理", "偏差", "局限", "safety", "ethics", "bias", "limit")
    ):
        return KnowledgeType.CONCEPT
    if any(
        token in name
        for token in (
            "实现",
            "编程",
            "代码",
            "实验",
            "提取",
            "分类",
            "coding",
            "implement",
            "extract",
        )
    ):
        return KnowledgeType.PROCEDURE
    if any(token in lowered for token in ("python", "array", "数组")):
        return KnowledgeType.PROCEDURE
    return KnowledgeType.CONCEPT


def build_course_modules(course: Course, *, path_id: str) -> list[LearningModule]:
    module_id = f"{path_id}_m0"
    knowledge_points = [
        KnowledgePoint(
            id=f"{module_id}_kp{index}",
            name=name.strip()[:200],
            type=_default_knowledge_type(name),
            module_id=module_id,
        )
        for index, name in enumerate(course.knowledge_points)
        if str(name).strip()
    ]
    if not knowledge_points:
        return []
    return [
        LearningModule(
            id=module_id,
            name=(course.title_zh or course.title_en or course.id)[:200],
            order=0,
            knowledge_points=knowledge_points,
        )
    ]


def ensure_course_mastery_path(
    course: Course,
    *,
    textbook_id: str | None = None,
    path_id: str | None = None,
    service: LearningService | None = None,
) -> LearningProgress:
    """Seed an empty mastery path from the catalog so progress is never blank."""
    resolved_path_id = path_id or build_mastery_path_id(textbook_id or "course", course.id)
    learning = service or LearningService(LearningStore())
    progress = learning.get_or_create(resolved_path_id)
    if progress.modules:
        return progress
    modules = build_course_modules(course, path_id=resolved_path_id)
    if not modules:
        return progress
    learning.replace_modules(progress, modules)
    progress.current_module_id = modules[0].id
    progress.current_kp_index = 0
    learning.save(progress)
    return progress


__all__ = [
    "build_course_modules",
    "ensure_course_mastery_path",
]
