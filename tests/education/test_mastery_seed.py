from pathlib import Path

from deeptutor.education.catalog import load_catalog
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore


def test_ensure_course_mastery_path_seeds_catalog_points(tmp_path: Path):
    textbook = load_catalog().textbooks[1]
    course = textbook.courses[0]
    store = LearningStore(root=tmp_path / "learning")
    service = LearningService(store)

    first = ensure_course_mastery_path(
        course,
        textbook_id=textbook.id,
        service=service,
    )
    second = ensure_course_mastery_path(
        course,
        textbook_id=textbook.id,
        service=service,
    )

    assert first.book_id == "edu_k12_ai_primary_upper_image_recognition"
    assert len(first.modules) == 1
    assert [kp.name for kp in first.modules[0].knowledge_points] == course.knowledge_points
    assert first.modules[0].knowledge_points[0].type.value in {
        "concept",
        "procedure",
        "memory",
        "design",
    }
    assert second.version == first.version
    assert second.modules[0].id == first.modules[0].id
