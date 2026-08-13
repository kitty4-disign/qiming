"""M1 acceptance test: quiz attempt updates the K12 mastery path and the
dashboard reflects the change."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import deeptutor.api.routers.education as education_module
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.learning.models import ErrorType, QuizAttempt
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
            "preferred_modalities": ["dialogue", "quiz"],
            "learning_goal": "理解图像识别",
        },
    )
    assert response.status_code == 200


def test_quiz_attempt_updates_k12_mastery_path(client: TestClient, tmp_path: Path):
    """A wrong quiz attempt must lower mastery and change the dashboard
    recommendation to weak_point."""
    _save_profile(client)

    # Get initial dashboard — should recommend next_new_point.
    dashboard = client.get("/api/v1/education/dashboard/image-recognition")
    assert dashboard.status_code == 200
    initial = dashboard.json()
    initial_reason_code = initial["recommendation"]["reasons"][0]["code"]
    assert initial_reason_code == "next_new_point"

    # Simulate a wrong quiz attempt on the first knowledge point.
    mastery_path_id = initial["mastery_path_id"]
    learning = LearningService(LearningStore(root=tmp_path / "learning"))
    progress = learning.get_or_create(mastery_path_id)
    kp_id = progress.modules[0].knowledge_points[0].id
    learning.grade_and_record(
        progress,
        question_id="q1",
        knowledge_point_id=kp_id,
        module_id=progress.modules[0].id,
        user_answer="wrong answer",
        expected_answer="correct answer",
        question_type="short",
    )

    # Dashboard should now recommend weak_point for that KP.
    dashboard_after = client.get("/api/v1/education/dashboard/image-recognition")
    assert dashboard_after.status_code == 200
    after = dashboard_after.json()
    assert after["recommendation"]["reasons"][0]["code"] == "weak_point"
    assert after["recommendation"]["knowledge_point_id"] == kp_id
    assert after["mastery_summary"]["learning"] >= 1


def test_dashboard_returns_specific_knowledge_point_name(client: TestClient):
    """The dashboard must return a concrete knowledge point name, not just a
    count."""
    _save_profile(client)
    dashboard = client.get("/api/v1/education/dashboard/image-recognition")
    assert dashboard.status_code == 200
    body = dashboard.json()
    rec = body["recommendation"]
    # The recommended knowledge point must have a non-empty name.
    assert rec["knowledge_point_name"]
    assert rec["knowledge_point_id"]


def test_record_event_and_summarize(client: TestClient):
    """POST /events records a learning event and the dashboard includes it."""
    _save_profile(client)
    completion = {
        "course_id": "image-recognition",
        "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
        "activity": "quiz",
        "event_type": "completed",
        "knowledge_point_id": "kp0",
        "score": 0.5,
        "duration_seconds": 30,
        "idempotency_key": "test-key-1",
    }
    response = client.post("/api/v1/education/events", json=completion)
    assert response.status_code == 200
    event = response.json()["event"]
    assert event["activity"] == "quiz"
    assert event["score"] == 0.5

    # Idempotent: same key returns same event.
    response2 = client.post("/api/v1/education/events", json=completion)
    assert response2.status_code == 200
    assert response2.json()["event"]["id"] == event["id"]

    # Dashboard shows the event in recent_events.
    dashboard = client.get("/api/v1/education/dashboard/image-recognition")
    assert dashboard.status_code == 200
    events = dashboard.json()["recent_events"]
    assert len(events) >= 1
    assert events[0]["activity"] == "quiz"
