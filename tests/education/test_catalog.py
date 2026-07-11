import pytest

from deeptutor.education.catalog import (
    load_catalog,
    resolve_curriculum,
    resolve_visible_knowledge_bases,
)
from deeptutor.education.models import EducationStage, StudentProfile
from deeptutor.education.path_ids import build_mastery_path_id


def profile(stage=EducationStage.PRIMARY_UPPER, textbook_id="k12-ai-primary-upper"):
    return StudentProfile(stage=stage, grade=5, textbook_id=textbook_id)


def test_catalog_contains_one_default_textbook_per_stage():
    catalog = load_catalog()
    stages = {item.stage.value for item in catalog.textbooks}
    assert stages == {"primary_lower", "primary_upper", "middle", "high"}


def test_resolve_curriculum_rejects_cross_stage_textbook():
    with pytest.raises(ValueError, match="does not belong to stage"):
        resolve_curriculum(profile(textbook_id="k12-ai-high"))


def test_kb_routing_returns_warning_when_catalog_kb_is_not_visible():
    names, warnings = resolve_visible_knowledge_bases(profile(), visible_names=set())
    assert names == []
    assert warnings == ["knowledge_base_not_ready:k12-ai-primary-upper"]


def test_kb_routing_uses_existing_visible_kb():
    names, warnings = resolve_visible_knowledge_bases(
        profile(), visible_names={"k12-ai-primary-upper"}
    )
    assert names == ["k12-ai-primary-upper"]
    assert warnings == []


def test_mastery_path_id_is_stable_and_storage_safe():
    assert build_mastery_path_id("k12-ai-primary-upper", "image-recognition") == (
        "edu_k12_ai_primary_upper_image_recognition"
    )
