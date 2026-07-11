from pathlib import Path

import pytest

import deeptutor.agents.k12_tutor.capability as k12_module
from deeptutor.agents.k12_tutor.capability import K12TutorCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.education.models import EducationStage, StudentProfile
from deeptutor.education.profile_service import EducationProfileService


@pytest.fixture
def profile_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EducationProfileService:
    service = EducationProfileService(path=tmp_path / "education_profile.json")
    service.save(
        StudentProfile(
            display_name="小航",
            stage=EducationStage.PRIMARY_UPPER,
            grade=5,
            textbook_id="k12-ai-primary-upper",
            interests=["机器人"],
            preferred_modalities=["dialogue", "quiz"],
            learning_goal="理解图像识别",
        )
    )
    monkeypatch.setattr(k12_module, "_profile_service", lambda: service)
    monkeypatch.setattr(k12_module, "list_visible_knowledge_bases", lambda: [])
    return service


@pytest.mark.asyncio
async def test_k12_capability_enables_mastery_and_uses_stable_path(
    monkeypatch: pytest.MonkeyPatch, profile_service: EducationProfileService
):
    captured = {}

    class FakePipeline:
        def __init__(self, language):
            captured["language"] = language

        async def run(self, context, stream):
            captured["context"] = context

    monkeypatch.setattr(k12_module, "AgenticChatPipeline", FakePipeline)
    context = UnifiedContext(
        session_id="session-1",
        user_message="开始学习",
        active_capability="k12_tutor",
        language="zh",
        config_overrides={
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
        },
    )
    await K12TutorCapability().run(context, StreamBus())
    assert captured["context"].metadata["mastery_mode"] is True
    assert captured["context"].metadata["mastery_path_id"] == (
        "edu_k12_ai_primary_upper_image_recognition"
    )
    assert "五年级" in captured["context"].persona_context
