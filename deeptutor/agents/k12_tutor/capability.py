from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.agents.k12_tutor.guidance import render_k12_guidance
from deeptutor.capabilities.mastery.tools import MASTERY_TOOL_NAMES
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.education.catalog import resolve_curriculum, resolve_visible_knowledge_bases
from deeptutor.education.path_ids import build_mastery_path_id
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.multi_user.knowledge_access import list_visible_knowledge_bases
from deeptutor.runtime.request_contracts import get_capability_request_schema


def _profile_service() -> EducationProfileService:
    return EducationProfileService()


class K12TutorCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="k12_tutor",
        description="Age-adaptive K12 AI literacy tutor backed by mastery learning.",
        stages=["responding"],
        tools_used=[*MASTERY_TOOL_NAMES, "rag", "read_source", "ask_user"],
        cli_aliases=["k12"],
        request_schema=get_capability_request_schema("k12_tutor"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        profile = _profile_service().load()
        if profile is None:
            raise ValueError("education_profile_required")
        textbook = resolve_curriculum(profile)
        course_id = str(context.config_overrides.get("course_id") or textbook.default_course_id)
        course = next((item for item in textbook.courses if item.id == course_id), None)
        if course is None:
            raise ValueError("course_not_found")
        expected_path = build_mastery_path_id(textbook.id, course.id)
        requested_path = str(context.config_overrides.get("mastery_path_id") or expected_path)
        if requested_path != expected_path:
            raise ValueError("invalid_mastery_path_id")

        visible = {str(item.get("name") or "") for item in list_visible_knowledge_bases()}
        knowledge_bases, warnings = resolve_visible_knowledge_bases(
            profile, visible_names=visible
        )
        context.knowledge_bases = knowledge_bases
        context.metadata["mastery_mode"] = True
        context.metadata["mastery_path_id"] = expected_path
        context.metadata["education_course_id"] = course.id
        context.metadata["education_warnings"] = warnings
        guidance = render_k12_guidance(profile, language=context.language)
        context.persona_context = "\n\n".join(
            part for part in (context.persona_context.strip(), guidance) if part
        )
        await AgenticChatPipeline(language=context.language).run(context, stream)
