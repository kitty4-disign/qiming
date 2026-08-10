from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.agents.k12_tutor.guidance import render_k12_guidance
from deeptutor.capabilities.mastery.tools import MASTERY_TOOL_NAMES
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.education.catalog import resolve_curriculum, resolve_visible_knowledge_bases
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.education.path_ids import build_mastery_path_id
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.education.teaching_policy import TeachingDecision, decide_teaching
from deeptutor.multi_user.knowledge_access import list_visible_knowledge_bases
from deeptutor.runtime.request_contracts import get_capability_request_schema


def _profile_service() -> EducationProfileService:
    return EducationProfileService()


def _teaching_decision_protocol(language: str, decision: TeachingDecision) -> str:
    """Turn a deterministic policy decision into live tutor constraints."""
    reasons = ", ".join(decision.reason_codes) or "none"
    if str(language).lower().startswith("zh"):
        return (
            "服务端教学策略（本轮必须执行）：\n"
            f"- 活动：{decision.activity}\n"
            f"- 难度级别：{decision.difficulty}/4；解释深度：{decision.explanation_depth}/4\n"
            f"- 提示强度：{decision.hint_level}\n"
            f"- 建议本轮问题预算：{decision.question_count}\n"
            f"- 可使用代码教学：{'是' if decision.use_code else '否'}；"
            f"可使用可视化：{'是' if decision.use_visualization else '否'}\n"
            f"- 当前策略知识点：{decision.knowledge_point_id or '按 mastery_status 决定'}\n"
            f"- 策略原因：{reasons}\n"
            "这些参数用于控制教学方式，但知识点推进顺序仍以 mastery_status 的硬门控为准。"
        )
    return (
        "Server teaching policy (must shape this turn):\n"
        f"- activity: {decision.activity}\n"
        f"- difficulty: {decision.difficulty}/4; explanation depth: {decision.explanation_depth}/4\n"
        f"- hint level: {decision.hint_level}\n"
        f"- suggested question budget: {decision.question_count}\n"
        f"- code teaching allowed: {decision.use_code}; visualization allowed: {decision.use_visualization}\n"
        f"- policy knowledge point: {decision.knowledge_point_id or 'follow mastery_status'}\n"
        f"- reason codes: {reasons}\n"
        "These parameters control pedagogy; mastery_status remains authoritative for objective ordering."
    )


def _turn_boundary_protocol(
    language: str,
    activity_mode: str,
    *,
    quiz_answered_count: int = 0,
    quiz_question_count: int = 3,
) -> str:
    """Hard protocol appended after normal guidance so turn semantics win."""
    total = max(1, min(10, int(quiz_question_count or 3)))
    answered = max(0, min(total, int(quiz_answered_count or 0)))
    zh = str(language).lower().startswith("zh")

    if zh:
        common = (
            "K12 跨轮次协议（硬性要求，优先级高于上方活动说明）：\n"
            "- ask_user 是当前 turn 的终点；调用 ask_user 后绝不能在同一 turn 中继续 mastery_grade。\n"
            "- 每个新 turn 都必须先调用 mastery_status。若状态显示有 pending answer，必须先用 "
            "mastery_grade 批改学习者刚提交的答案，再解释反馈。\n"
            "- 除测验轮次达到其明确题数上限外，若 mastery_status / mastery_grade 的 next.action"
            " 不是 complete，反馈后不能直接用无工具文本结束；必须继续一个最小教学步骤，并最终用"
            "恰好一个 ask_user 问题结束 turn。\n"
            "- 不得让学习者输入“继续”才能恢复正常教学；只要当前活动仍需推进，本轮就要主动推进到"
            "下一个可回答的问题。\n"
        )
        if activity_mode != "quiz":
            return common
        if answered >= total:
            return common + (
                f"测验状态（服务端计数）：已提交 {answered}/{total} 题。"
                f"本轮只负责批改第 {total} 题：先 mastery_status，再 mastery_grade，给出第 {total} 题"
                "即时反馈和本轮测验总结。题数上限优先于课程是否 complete；本轮绝对禁止再次调用 "
                "mastery_quiz 或 ask_user，禁止生成第 4 题/额外题，然后以正常文本结束本轮测验。"
            )
        if answered == 0:
            return common + (
                f"测验状态（服务端计数）：已提交 0/{total} 题。当前是测验启动轮；读取 mastery_status "
                "后注册第 1 题并用 ask_user 展示。每次只允许注册一题。"
            )
        return common + (
            f"测验状态（服务端计数）：学习者刚提交第 {answered}/{total} 题的答案。先批改第 {answered} "
            f"题并给即时反馈；随后注册第 {answered + 1} 题并用 ask_user 展示。"
            "不得跳题、重复计数或一次展示多题。"
        )

    common = (
        "K12 cross-turn protocol (hard requirement; overrides conflicting activity text above):\n"
        "- ask_user ENDS the current turn. Never call mastery_grade after ask_user in the same turn.\n"
        "- Every new turn starts with mastery_status. If it reports a pending answer, call mastery_grade "
        "first to grade the learner's submitted answer, then explain the feedback.\n"
        "- Except when a quiz has reached its explicit question limit, if next.action is not complete, "
        "do not end with tool-less feedback. Continue one minimal teaching step and finish the turn with "
        "exactly one ask_user question.\n"
        "- Never require the learner to type 'continue' to resume normal teaching; proactively advance "
        "while the current activity still has work to do.\n"
    )
    if activity_mode != "quiz":
        return common
    if answered >= total:
        return common + (
            f"Quiz state (server counted): {answered}/{total} answers submitted. This turn only grades "
            f"question {total}: call mastery_status, then mastery_grade, give immediate feedback and a quiz "
            "summary. The quiz question limit takes precedence over course completion: do NOT call "
            "mastery_quiz or ask_user again, do NOT create an extra question, and finish with normal text."
        )
    if answered == 0:
        return common + (
            f"Quiz state (server counted): 0/{total} answers submitted. This is the launch turn; after "
            "mastery_status register question 1 and present it with ask_user. Register only one question."
        )
    return common + (
        f"Quiz state (server counted): the learner just submitted answer {answered}/{total}. Grade question "
        f"{answered} first and give immediate feedback; then register question {answered + 1} and present "
        "it with ask_user. Never skip, double-count, or show multiple questions at once."
    )


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
        education_context = context.education_context
        if education_context is not None and (
            education_context.stage != profile.stage.value
            or education_context.grade != profile.grade
        ):
            raise ValueError("education_context_profile_mismatch")
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
        progress = ensure_course_mastery_path(
            course,
            textbook_id=textbook.id,
            path_id=expected_path,
        )
        context.knowledge_bases = knowledge_bases
        context.metadata["mastery_mode"] = True
        context.metadata["mastery_path_id"] = expected_path
        context.metadata["education_course_id"] = course.id
        context.metadata["education_warnings"] = warnings
        context.metadata["ask_user_turn_boundary"] = True
        context.metadata["_min_loop_rounds"] = 10
        activity_mode = str(context.config_overrides.get("activity_mode") or "lesson")
        context.metadata["education_activity_mode"] = activity_mode

        quiz_question_count = max(
            1,
            min(10, int(context.config_overrides.get("quiz_question_count") or 3)),
        )
        quiz_answered_count = max(
            0,
            min(
                quiz_question_count,
                int(context.config_overrides.get("quiz_answered_count") or 0),
            ),
        )
        if activity_mode == "quiz":
            context.metadata["education_quiz_question_count"] = quiz_question_count
            context.metadata["education_quiz_answered_count"] = quiz_answered_count
            context.metadata["education_quiz_limit_reached"] = (
                quiz_answered_count >= quiz_question_count
            )

        policy_decision = decide_teaching(
            profile=profile,
            progress=progress,
            allowed_modalities=list(course.recommended_actions),
        )
        # The learner explicitly chose this activity in the dashboard. Policy
        # controls how it is taught, while the explicit launch controls what
        # activity is being run. Exact quiz length is also a product contract.
        policy_updates: dict[str, object] = {"activity": activity_mode}
        if activity_mode == "quiz":
            policy_updates["question_count"] = quiz_question_count
        effective_decision = policy_decision.model_copy(update=policy_updates)
        context.metadata["education_teaching_decision"] = effective_decision.model_dump(
            mode="json"
        )

        target_knowledge_point = None
        if education_context is not None and education_context.knowledge_point_id:
            target_knowledge_point = next(
                (
                    point
                    for module in progress.modules
                    for point in module.knowledge_points
                    if point.id == education_context.knowledge_point_id
                ),
                None,
            )
            if target_knowledge_point is None:
                raise ValueError("knowledge_point_not_found")
            context.metadata["education_knowledge_point_id"] = target_knowledge_point.id
            context.metadata["education_knowledge_point_name"] = target_knowledge_point.name
        guidance = render_k12_guidance(
            profile,
            language=context.language,
            activity_mode=activity_mode,
            target_knowledge_point_name=(
                target_knowledge_point.name if target_knowledge_point else ""
            ),
            target_knowledge_point_id=(
                target_knowledge_point.id if target_knowledge_point else ""
            ),
        )
        teaching_protocol = _teaching_decision_protocol(context.language, effective_decision)
        boundary_protocol = _turn_boundary_protocol(
            context.language,
            activity_mode,
            quiz_answered_count=quiz_answered_count,
            quiz_question_count=quiz_question_count,
        )
        context.persona_context = "\n\n".join(
            part
            for part in (
                context.persona_context.strip(),
                guidance,
                teaching_protocol,
                boundary_protocol,
            )
            if part
        )
        await AgenticChatPipeline(language=context.language).run(context, stream)
