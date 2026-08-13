from fastapi import APIRouter, HTTPException

from deeptutor.education.activity_models import ActivityCompletion
from deeptutor.education.activity_service import EducationActivityService
from deeptutor.education.catalog import (
    load_catalog,
    resolve_curriculum,
    resolve_visible_knowledge_bases,
)
from deeptutor.education.code_runner import CodeRunError, run_student_code
from deeptutor.education.coding_models import CodeRunRequest
from deeptutor.education.coding_tasks import get_coding_task, list_coding_tasks
from deeptutor.education.episode_models import CompleteEpisodeRequest, CreateEpisodeRequest
from deeptutor.education.episode_service import EpisodeConflictError, LearningEpisodeService
from deeptutor.education.gamification import compute_gamification
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.education.models import StudentProfile
from deeptutor.education.path_ids import build_mastery_path_id
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.education.recommender import (
    RecommendationContext,
    recommend,
    summarize_mastery,
)
from deeptutor.education.teaching_policy import decide_teaching
from deeptutor.learning.policy import display_mastery, find_knowledge_point
from deeptutor.multi_user.knowledge_access import list_visible_knowledge_bases

router = APIRouter()


def _profile_service() -> EducationProfileService:
    return EducationProfileService()


def _activity_service() -> EducationActivityService:
    return EducationActivityService()


def _episode_service() -> LearningEpisodeService:
    return LearningEpisodeService()


def _course_context(course_id: str):
    profile = _profile_service().load()
    if profile is None:
        raise HTTPException(status_code=409, detail="education_profile_required")
    textbook = resolve_curriculum(profile)
    course = next((item for item in textbook.courses if item.id == course_id), None)
    if course is None:
        raise HTTPException(status_code=404, detail="course_not_found")
    mastery_path_id = build_mastery_path_id(textbook.id, course.id)
    progress = ensure_course_mastery_path(
        course, textbook_id=textbook.id, path_id=mastery_path_id
    )
    return profile, textbook, course, mastery_path_id, progress


def _knowledge_point(progress, knowledge_point_id: str):
    kp, _, _ = find_knowledge_point(progress, knowledge_point_id)
    if kp is None:
        raise HTTPException(status_code=422, detail="knowledge_point_not_in_course")
    return kp


@router.get("/profile")
async def get_profile():
    profile = _profile_service().load()
    return {"profile": profile.model_dump(mode="json") if profile else None}


@router.put("/profile")
async def put_profile(profile: StudentProfile):
    try:
        resolve_curriculum(profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    saved = _profile_service().save(profile)
    return {"profile": saved.model_dump(mode="json")}


@router.get("/catalog")
async def get_catalog():
    return load_catalog().model_dump(mode="json")


@router.get("/launch-context/{course_id}")
async def get_launch_context(course_id: str):
    profile = _profile_service().load()
    if profile is None:
        raise HTTPException(status_code=409, detail="education_profile_required")
    textbook = resolve_curriculum(profile)
    course = next((item for item in textbook.courses if item.id == course_id), None)
    if course is None:
        raise HTTPException(status_code=404, detail="course_not_found")
    visible_names = {str(item.get("name") or "") for item in list_visible_knowledge_bases()}
    knowledge_bases, warnings = resolve_visible_knowledge_bases(
        profile, visible_names=visible_names
    )
    mastery_path_id = build_mastery_path_id(textbook.id, course.id)
    progress = ensure_course_mastery_path(
        course,
        textbook_id=textbook.id,
        path_id=mastery_path_id,
    )
    return {
        "profile": profile.model_dump(mode="json"),
        "textbook": textbook.model_dump(mode="json"),
        "course": course.model_dump(mode="json"),
        "mastery_path_id": mastery_path_id,
        "knowledge_bases": knowledge_bases,
        "warnings": warnings,
        "mastery_seeded": bool(progress.modules),
        "mastery_counts": {
            "total": sum(len(module.knowledge_points) for module in progress.modules),
            "modules": len(progress.modules),
        },
    }


@router.post("/events")
async def record_event(completion: ActivityCompletion):
    """Record a learning activity event for the current user.

    Idempotency is enforced via ``idempotency_key``: a repeated ``completed``
    request with the same key returns the existing event instead of creating a
    duplicate, preventing double-credit on page refresh.
    """
    _, _, _, mastery_path_id, _ = _course_context(completion.course_id)
    if completion.mastery_path_id != mastery_path_id:
        raise HTTPException(status_code=422, detail="mastery_path_mismatch")
    if completion.episode_id:
        episode = _episode_service().get(completion.episode_id)
        if episode is None or episode.course_id != completion.course_id:
            raise HTTPException(status_code=422, detail="episode_mismatch")
        if completion.knowledge_point_id != episode.knowledge_point_id:
            raise HTTPException(status_code=422, detail="knowledge_point_not_in_episode")
    event = _activity_service().record(completion)
    return {"event": event.model_dump(mode="json")}


@router.get("/events")
async def list_events(course_id: str | None = None, limit: int = 50):
    """Return recent learning events, optionally filtered by course."""
    service = _activity_service()
    if course_id:
        events = service.list_for_course(course_id, limit=limit)
    else:
        events = service.list_recent(limit=limit)
    return {"events": [event.model_dump(mode="json") for event in events]}


@router.get("/dashboard/{course_id}")
async def get_dashboard(course_id: str):
    """One-call workspace data: profile, course, mastery, recommendation, events.

    The frontend should not need to fan out four-to-six requests just to render
    the education workspace.  This endpoint aggregates everything in one round
    trip so the dashboard renders immediately and the recommendation is always
    consistent with the persisted mastery state.
    """
    profile, _, course, mastery_path_id, progress = _course_context(course_id)
    activity_service = _activity_service()
    recent_events = activity_service.list_for_course(course_id, limit=20)
    activity_summary = activity_service.summarize(course_id)

    ctx = RecommendationContext(
        profile=profile,
        course_id=course.id,
        course_title=course.title_zh or course.title_en,
        knowledge_points=list(course.knowledge_points),
        recommended_actions=list(course.recommended_actions),
        mastery_path_id=mastery_path_id,
        progress=progress,
    )
    recommendation = recommend(ctx)
    mastery_summary = summarize_mastery(progress)
    episode_service = _episode_service()
    active_episode = episode_service.current(course_id=course_id)
    completed_episodes = [
        item for item in episode_service.list_recent(course_id=course_id, limit=10)
        if item.status == "completed"
    ]
    decision = decide_teaching(
        profile=profile,
        progress=progress,
        allowed_modalities=list(course.recommended_actions),
        misconceptions=(active_episode.initial_misconceptions if active_episode else []),
    )

    return {
        "profile": profile.model_dump(mode="json"),
        "course": course.model_dump(mode="json"),
        "mastery_path_id": mastery_path_id,
        "mastery_summary": mastery_summary,
        "recommendation": recommendation.model_dump(mode="json"),
        "activity_summary": activity_summary,
        "recent_events": [event.model_dump(mode="json") for event in recent_events],
        "active_episode": active_episode.evidence_dump() if active_episode else None,
        "learning_evidence": completed_episodes[0].evidence_dump() if completed_episodes else None,
        "teaching_decision": decision.model_dump(mode="json"),
    }


@router.post("/episodes")
async def create_episode(request: CreateEpisodeRequest):
    profile, _, _, mastery_path_id, progress = _course_context(request.course_id)
    kp = _knowledge_point(progress, request.knowledge_point_id)
    episode = _episode_service().create(
        course_id=request.course_id,
        mastery_path_id=mastery_path_id,
        knowledge_point_id=kp.id,
        knowledge_point_name=kp.name,
        stage=profile.stage,
        pre_score=request.pre_score,
        initial_misconceptions=request.initial_misconceptions,
        mastery_before=display_mastery(progress, kp),
    )
    return {"episode": episode.evidence_dump()}


@router.get("/episodes/current")
async def get_current_episode(course_id: str | None = None):
    episode = _episode_service().current(course_id=course_id)
    return {"episode": episode.evidence_dump() if episode else None}


@router.get("/episodes/{episode_id}")
async def get_episode(episode_id: str):
    episode = _episode_service().get(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="episode_not_found")
    return {"episode": episode.evidence_dump()}


@router.post("/episodes/{episode_id}/complete")
async def complete_episode(episode_id: str, request: CompleteEpisodeRequest):
    existing = _episode_service().get(episode_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="episode_not_found")
    _, _, _, mastery_path_id, progress = _course_context(existing.course_id)
    if existing.mastery_path_id != mastery_path_id:
        raise HTTPException(status_code=422, detail="mastery_path_mismatch")
    kp = _knowledge_point(progress, existing.knowledge_point_id)
    try:
        episode = _episode_service().complete(
            episode_id,
            post_score=request.post_score,
            resolved_misconceptions=request.resolved_misconceptions,
            activities_used=request.activities_used,
            activity_reasons=request.activity_reasons,
            source_ids=request.source_ids,
            mastery_after=display_mastery(progress, kp),
        )
    except EpisodeConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"episode": episode.evidence_dump()}


@router.get("/coding-tasks")
async def list_tasks(course_id: str | None = None):
    """List coding tasks. Hidden tests and hints are stripped from the response."""
    tasks = list_coding_tasks(course_id)
    return {
        "tasks": [
            {
                "id": t.id,
                "course_id": t.course_id,
                "stage": t.stage.value,
                "title": t.title,
                "instructions": t.instructions,
                "starter_code": t.starter_code,
                "allowed_languages": t.allowed_languages,
                "visible_tests": [tc.model_dump(mode="json") for tc in t.visible_tests],
                "hint_count": len(t.hints),
            }
            for t in tasks
        ]
    }


@router.get("/coding-tasks/{task_id}")
async def get_task(task_id: str):
    """Get a coding task. Hidden tests are never returned; hints are returned
    one at a time via the hint endpoint."""
    task = get_coding_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return {
        "id": task.id,
        "course_id": task.course_id,
        "stage": task.stage.value,
        "title": task.title,
        "instructions": task.instructions,
        "starter_code": task.starter_code,
        "allowed_languages": task.allowed_languages,
        "visible_tests": [tc.model_dump(mode="json") for tc in task.visible_tests],
        "hint_count": len(task.hints),
    }


@router.post("/code/run")
async def run_code(request: CodeRunRequest):
    """Run student code in the sandbox and evaluate against tests.

    Returns 503 when the sandbox is unavailable — never silently fakes success.
    """
    try:
        result = await run_student_code(request)
    except CodeRunError as exc:
        detail = str(exc)
        status = 503 if detail == "sandbox_unavailable" else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return {"result": result.model_dump(mode="json")}


@router.get("/coding-tasks/{task_id}/hint")
async def get_hint(task_id: str, attempt: int = 0):
    """Progressive hint. First attempt (attempt=0) gives guidance, never the
    full answer."""
    from deeptutor.education.code_runner import get_hint as _get_hint

    task = get_coding_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return {"hint": _get_hint(task, attempt)}


@router.get("/gamification/{course_id}")
async def get_gamification(course_id: str):
    """Derive gamification state from real learning records.

    Pure derivation: same inputs always produce same outputs. Refresh never
    inflates XP or badges because nothing is stored — it is recomputed from
    mastery + events on every call.
    """
    profile = _profile_service().load()
    if profile is None:
        raise HTTPException(status_code=409, detail="education_profile_required")
    textbook = resolve_curriculum(profile)
    course = next((item for item in textbook.courses if item.id == course_id), None)
    if course is None:
        raise HTTPException(status_code=404, detail="course_not_found")
    mastery_path_id = build_mastery_path_id(textbook.id, course.id)
    progress = ensure_course_mastery_path(
        course,
        textbook_id=textbook.id,
        path_id=mastery_path_id,
    )
    events = _activity_service().list_for_course(course_id, limit=500)
    summary = compute_gamification(progress, events)
    return {"gamification": summary.__dict__}
