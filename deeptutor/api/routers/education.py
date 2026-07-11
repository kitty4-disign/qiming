from fastapi import APIRouter, HTTPException

from deeptutor.education.catalog import (
    load_catalog,
    resolve_curriculum,
    resolve_visible_knowledge_bases,
)
from deeptutor.education.models import StudentProfile
from deeptutor.education.path_ids import build_mastery_path_id
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.multi_user.knowledge_access import list_visible_knowledge_bases

router = APIRouter()


def _profile_service() -> EducationProfileService:
    return EducationProfileService()


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
    return {
        "profile": profile.model_dump(mode="json"),
        "textbook": textbook.model_dump(mode="json"),
        "course": course.model_dump(mode="json"),
        "mastery_path_id": build_mastery_path_id(textbook.id, course.id),
        "knowledge_bases": knowledge_bases,
        "warnings": warnings,
    }
