"""M4 §9.2 catalog v2 acceptance tests.

Verifies:
- Catalog upgraded to v2 with all v2 fields present and non-empty for the
  flagship course of each stage.
- Each stage has at least 2 courses (flagship + second course).
- v1 backward compatibility: v2 fields all have defaults, so a v1-style course
  still validates.
- Coding task ids referenced in catalog exist in coding_tasks fixture.
"""

from __future__ import annotations

import pytest

from deeptutor.education.catalog import Course, CurriculumCatalog, Textbook, load_catalog
from deeptutor.education.coding_tasks import get_coding_task
from deeptutor.education.models import EducationStage


@pytest.fixture
def catalog() -> CurriculumCatalog:
    return load_catalog()


def test_catalog_is_version_2(catalog: CurriculumCatalog):
    assert catalog.version == 2


def test_each_textbook_has_at_least_two_courses(catalog: CurriculumCatalog):
    for textbook in catalog.textbooks:
        assert len(textbook.courses) >= 2, f"{textbook.id} has only {len(textbook.courses)} course(s)"


def test_each_stage_has_flagship_and_second_course(catalog: CurriculumCatalog):
    stages_seen = {t.stage for t in catalog.textbooks}
    assert stages_seen == {
        EducationStage.PRIMARY_LOWER,
        EducationStage.PRIMARY_UPPER,
        EducationStage.MIDDLE,
        EducationStage.HIGH,
    }


def test_flagship_courses_have_all_v2_fields(catalog: CurriculumCatalog):
    """The flagship course of each stage must have all v2 fields populated."""
    for textbook in catalog.textbooks:
        course = next(c for c in textbook.courses if c.id == textbook.default_course_id)
        assert course.prerequisite_ids is not None, f"{course.id}: prerequisite_ids missing"
        assert course.estimated_minutes >= 1, f"{course.id}: estimated_minutes invalid"
        assert 1 <= course.difficulty <= 5, f"{course.id}: difficulty invalid"
        assert course.age_policy, f"{course.id}: age_policy empty"
        assert course.default_knowledge_point_id, f"{course.id}: default_knowledge_point_id empty"
        assert course.learning_objectives, f"{course.id}: learning_objectives empty"
        assert course.common_misconceptions, f"{course.id}: common_misconceptions empty"
        assert course.safety_notes, f"{course.id}: safety_notes empty"
        assert course.reference_sources, f"{course.id}: reference_sources empty"


def test_second_courses_have_prerequisites(catalog: CurriculumCatalog):
    """Second courses must list their prerequisite as the flagship course."""
    for textbook in catalog.textbooks:
        second_courses = [c for c in textbook.courses if c.id != textbook.default_course_id]
        assert second_courses, f"{textbook.id}: no second course"
        for course in second_courses:
            assert textbook.default_course_id in course.prerequisite_ids, (
                f"{course.id}: prerequisite must include {textbook.default_course_id}"
            )


def test_coding_task_ids_resolve(catalog: CurriculumCatalog):
    """Every coding_task_id referenced in catalog must exist in the fixture."""
    for textbook in catalog.textbooks:
        for course in textbook.courses:
            for task_id in course.coding_task_ids:
                assert get_coding_task(task_id) is not None, (
                    f"{course.id} references unknown coding task: {task_id}"
                )


def test_v1_backward_compatibility():
    """A v1-style course (no v2 fields) must still validate."""
    v1_course = Course(
        id="v1-test",
        title_zh="测试",
        title_en="Test",
        summary_zh="测试课程",
        knowledge_points=["知识点1"],
        recommended_actions=["dialogue"],
    )
    assert v1_course.prerequisite_ids == []
    assert v1_course.estimated_minutes == 20
    assert v1_course.difficulty == 1
    assert v1_course.age_policy == ""
    assert v1_course.learning_objectives == []


def test_difficulty_increases_with_stage(catalog: CurriculumCatalog):
    """Flagship course difficulty should roughly increase with stage."""
    by_stage = {}
    for textbook in catalog.textbooks:
        course = next(c for c in textbook.courses if c.id == textbook.default_course_id)
        by_stage[textbook.stage] = course.difficulty
    assert by_stage[EducationStage.PRIMARY_LOWER] <= by_stage[EducationStage.PRIMARY_UPPER]
    assert by_stage[EducationStage.PRIMARY_UPPER] <= by_stage[EducationStage.MIDDLE]
    assert by_stage[EducationStage.MIDDLE] <= by_stage[EducationStage.HIGH]
