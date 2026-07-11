from pathlib import Path

import pytest

from deeptutor.education.models import EducationStage, StudentProfile
from deeptutor.education.profile_service import EducationProfileService


def valid_profile(**overrides):
    payload = {
        "display_name": "小航",
        "stage": EducationStage.PRIMARY_UPPER,
        "grade": 5,
        "textbook_id": "k12-ai-primary-upper",
        "interests": ["机器人", "绘画"],
        "preferred_modalities": ["dialogue", "storybook", "quiz"],
        "learning_goal": "理解图像识别是怎样学习的",
    }
    payload.update(overrides)
    return StudentProfile(**payload)


def test_profile_rejects_grade_outside_stage():
    with pytest.raises(ValueError, match="grade must be between 4 and 6"):
        valid_profile(grade=8)


def test_profile_rejects_unknown_modality():
    with pytest.raises(ValueError):
        valid_profile(preferred_modalities=["telepathy"])


def test_service_returns_none_when_profile_does_not_exist(tmp_path: Path):
    service = EducationProfileService(path=tmp_path / "education_profile.json")
    assert service.load() is None


def test_service_round_trips_normalized_profile(tmp_path: Path):
    service = EducationProfileService(path=tmp_path / "education_profile.json")
    saved = service.save(valid_profile(interests=[" 机器人 ", "机器人", " 绘画 "]))
    loaded = service.load()
    assert saved == loaded
    assert loaded is not None
    assert loaded.interests == ["机器人", "绘画"]
