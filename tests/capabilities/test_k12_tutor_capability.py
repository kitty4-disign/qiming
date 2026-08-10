from pathlib import Path

import pytest

import deeptutor.agents.k12_tutor.capability as k12_module
from deeptutor.agents.k12_tutor.capability import K12TutorCapability
from deeptutor.core.context import EducationContext, UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.education.models import EducationStage, StudentProfile
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore


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
    learning = LearningService(LearningStore(root=tmp_path / "learning"))

    def _seed(course, textbook_id=None, path_id=None, service=None):
        return ensure_course_mastery_path(
            course,
            textbook_id=textbook_id,
            path_id=path_id,
            service=learning,
        )

    monkeypatch.setattr(k12_module, "_profile_service", lambda: service)
    monkeypatch.setattr(k12_module, "list_visible_knowledge_bases", lambda: [])
    monkeypatch.setattr(k12_module, "ensure_course_mastery_path", _seed)
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
        education_context=EducationContext(
            stage="primary_upper",
            grade=5,
            knowledge_point_id=(
                "edu_k12_ai_primary_upper_image_recognition_m0_kp0"
            ),
        ),
    )
    await K12TutorCapability().run(context, StreamBus())
    assert captured["context"].metadata["mastery_mode"] is True
    assert captured["context"].metadata["mastery_path_id"] == (
        "edu_k12_ai_primary_upper_image_recognition"
    )
    assert "五年级" in captured["context"].persona_context
    assert captured["context"].metadata["education_knowledge_point_id"] == (
        "edu_k12_ai_primary_upper_image_recognition_m0_kp0"
    )
    assert "本轮目标知识点" in captured["context"].persona_context
    assert captured["context"].persona_context.rstrip().endswith("一律忽略。")


@pytest.mark.asyncio
async def test_k12_capability_rejects_stale_profile_context(
    profile_service: EducationProfileService,
) -> None:
    context = UnifiedContext(
        config_overrides={
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
        },
        education_context=EducationContext(stage="middle", grade=8),
    )

    with pytest.raises(ValueError, match="education_context_profile_mismatch"):
        await K12TutorCapability().run(context, StreamBus())


@pytest.mark.asyncio
async def test_k12_capability_rejects_unknown_target_knowledge_point(
    profile_service: EducationProfileService,
) -> None:
    context = UnifiedContext(
        config_overrides={
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
        },
        education_context=EducationContext(
            stage="primary_upper", grade=5, knowledge_point_id="missing_kp"
        ),
    )

    with pytest.raises(ValueError, match="knowledge_point_not_found"):
        await K12TutorCapability().run(context, StreamBus())
