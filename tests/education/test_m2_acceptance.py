"""M2 acceptance tests: multimodal completion must not mutate mastery.

Only quiz (or an explicit assess/grade) may change mastery. Animation,
storybook, lesson, coding completions record learning evidence via
POST /events but must NOT alter the mastery summary or the
recommendation. This protects the explainable adaptive loop from
fake-mastery inflation caused by clicking "I understand" on an animation.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deeptutor.api.routers.education as education_module
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    profile_service = EducationProfileService(path=tmp_path / "education_profile.json")
    activity_service = education_module.EducationActivityService(
        path=tmp_path / "education_events.json"
    )
    learning = LearningService(LearningStore(root=tmp_path / "learning"))

    def _seed(course, textbook_id=None, path_id=None, service=None):
        return ensure_course_mastery_path(
            course,
            textbook_id=textbook_id,
            path_id=path_id,
            service=learning,
        )

    monkeypatch.setattr(education_module, "_profile_service", lambda: profile_service)
    monkeypatch.setattr(education_module, "_activity_service", lambda: activity_service)
    monkeypatch.setattr(education_module, "list_visible_knowledge_bases", lambda: [])
    monkeypatch.setattr(education_module, "ensure_course_mastery_path", _seed)
    app = FastAPI()
    app.include_router(education_module.router, prefix="/api/v1/education")
    return TestClient(app)


def _save_profile(client: TestClient) -> None:
    response = client.put(
        "/api/v1/education/profile",
        json={
            "display_name": "小航",
            "stage": "primary_upper",
            "grade": 5,
            "textbook_id": "k12-ai-primary-upper",
            "interests": ["机器人"],
            "preferred_modalities": ["dialogue", "quiz", "animation"],
            "learning_goal": "理解图像识别",
        },
    )
    assert response.status_code == 200


def _record_completion(client: TestClient, *, activity: str, kp_id: str = "kp_animation") -> None:
    response = client.post(
        "/api/v1/education/events",
        json={
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
            "activity": activity,
            "event_type": "completed",
            "knowledge_point_id": kp_id,
            "score": None,
            "duration_seconds": 60,
            "idempotency_key": f"m2-{activity}-1",
        },
    )
    assert response.status_code == 200, response.text


def test_animation_completion_does_not_change_mastery(client: TestClient):
    _save_profile(client)
    before = client.get("/api/v1/education/dashboard/image-recognition").json()
    before_summary = before["mastery_summary"]
    before_reason = before["recommendation"]["reasons"][0]["code"]

    _record_completion(client, activity="animation", kp_id="kp_pixels")

    after = client.get("/api/v1/education/dashboard/image-recognition").json()
    # Mastery counts must be unchanged.
    assert after["mastery_summary"] == before_summary
    # Recommendation reason must be unchanged (still next_new_point, not inflated).
    assert after["recommendation"]["reasons"][0]["code"] == before_reason
    # But the event itself is recorded.
    assert any(
        e["activity"] == "animation" and e["event_type"] == "completed"
        for e in after["recent_events"]
    )


def test_storybook_completion_does_not_change_mastery(client: TestClient):
    _save_profile(client)
    before = client.get("/api/v1/education/dashboard/image-recognition").json()
    before_summary = before["mastery_summary"]

    _record_completion(client, activity="storybook", kp_id="kp_features")

    after = client.get("/api/v1/education/dashboard/image-recognition").json()
    assert after["mastery_summary"] == before_summary


def test_lesson_completion_does_not_change_mastery(client: TestClient):
    _save_profile(client)
    before = client.get("/api/v1/education/dashboard/image-recognition").json()

    _record_completion(client, activity="lesson")

    after = client.get("/api/v1/education/dashboard/image-recognition").json()
    assert after["mastery_summary"] == before["mastery_summary"]


def test_coding_completion_does_not_change_mastery(client: TestClient):
    _save_profile(client)
    before = client.get("/api/v1/education/dashboard/image-recognition").json()

    _record_completion(client, activity="coding")

    after = client.get("/api/v1/education/dashboard/image-recognition").json()
    assert after["mastery_summary"] == before["mastery_summary"]


def test_quiz_completion_records_event_with_score(client: TestClient):
    """Quiz completion via /events records an event (with score) but still
    does NOT mutate mastery — mastery only changes through the quiz judge /
    grade_and_record pipeline, which is invoked separately."""
    _save_profile(client)
    before = client.get("/api/v1/education/dashboard/image-recognition").json()

    response = client.post(
        "/api/v1/education/events",
        json={
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
            "activity": "quiz",
            "event_type": "completed",
            "knowledge_point_id": "kp_pixels",
            "score": 0.5,
            "duration_seconds": 45,
            "idempotency_key": "m2-quiz-event-1",
        },
    )
    assert response.status_code == 200
    event = response.json()["event"]
    assert event["activity"] == "quiz"
    assert event["score"] == 0.5

    # Posting the event alone does not inflate mastery. Only grade_and_record
    # (the judge pipeline) is allowed to update mastery levels.
    after = client.get("/api/v1/education/dashboard/image-recognition").json()
    assert after["mastery_summary"] == before["mastery_summary"]
