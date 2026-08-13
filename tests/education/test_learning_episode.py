from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import deeptutor.api.routers.education as education_router
from deeptutor.education.activity_service import EducationActivityService
from deeptutor.education.episode_models import LearningEpisode
from deeptutor.education.episode_service import LearningEpisodeService
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.education.profile_service import EducationProfileService
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore


def test_learning_gain_is_deterministic():
    episode = LearningEpisode(
        episode_id="ep_test",
        course_id="course-a",
        mastery_path_id="path-a",
        knowledge_point_id="kp-a",
        stage="primary_upper",
        pre_score=25,
        post_score=75,
        status="completed",
    )

    assert episode.raw_gain == 50
    assert episode.normalized_gain == pytest.approx(2 / 3)


def test_scores_are_bounded():
    with pytest.raises(ValueError):
        LearningEpisode(
            episode_id="ep_test",
            course_id="course-a",
            mastery_path_id="path-a",
            knowledge_point_id="kp-a",
            stage="primary_upper",
            pre_score=0,
            post_score=101,
        )


def test_episode_persists_and_deduplicates_misconceptions(tmp_path: Path):
    path = tmp_path / "episodes.json"
    service = LearningEpisodeService(path)
    created = service.create(
        course_id="course-a",
        mastery_path_id="path-a",
        knowledge_point_id="kp-a",
        knowledge_point_name="KP A",
        stage="middle",
        pre_score=20,
        initial_misconceptions=["same", "same", "other"],
        mastery_before=0.1,
    )

    restored = LearningEpisodeService(path).current(course_id="course-a")
    assert restored is not None
    assert restored.episode_id == created.episode_id
    assert restored.initial_misconceptions == ["same", "other"]
    assert LearningEpisodeService(path).current(course_id="course-b") is None


@pytest.fixture
def episode_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    profile = EducationProfileService(tmp_path / "profile.json")
    episodes = LearningEpisodeService(tmp_path / "episodes.json")
    activities = EducationActivityService(tmp_path / "events.json")
    learning = LearningService(LearningStore(root=tmp_path / "learning"))

    def seed(course, textbook_id=None, path_id=None, service=None):
        return ensure_course_mastery_path(
            course, textbook_id=textbook_id, path_id=path_id, service=learning
        )

    monkeypatch.setattr(education_router, "_profile_service", lambda: profile)
    monkeypatch.setattr(education_router, "_episode_service", lambda: episodes)
    monkeypatch.setattr(education_router, "_activity_service", lambda: activities)
    monkeypatch.setattr(education_router, "ensure_course_mastery_path", seed)
    app = FastAPI()
    app.include_router(education_router.router, prefix="/api/v1/education")
    client = TestClient(app)
    response = client.put(
        "/api/v1/education/profile",
        json={
            "stage": "primary_upper",
            "grade": 5,
            "textbook_id": "k12-ai-primary-upper",
            "preferred_modalities": ["animation", "quiz"],
        },
    )
    assert response.status_code == 200
    return client


def test_episode_api_closes_learning_cycle(episode_client: TestClient):
    context = episode_client.get("/api/v1/education/launch-context/image-recognition").json()
    kp_id = f"{context['mastery_path_id']}_m0_kp0"
    created = episode_client.post(
        "/api/v1/education/episodes",
        json={
            "course_id": "image-recognition",
            "knowledge_point_id": kp_id,
            "pre_score": 25,
            "initial_misconceptions": ["测试集参与训练", "测试集参与训练"],
        },
    )
    assert created.status_code == 200
    episode_id = created.json()["episode"]["episode_id"]

    completed = episode_client.post(
        f"/api/v1/education/episodes/{episode_id}/complete",
        json={
            "post_score": 75,
            "resolved_misconceptions": ["测试集参与训练"],
            "activities_used": ["animation", "quiz"],
            "activity_reasons": ["REPEATED_MISCONCEPTION"],
            "source_ids": ["primary-upper-image-recognition.md#chunk-1"],
        },
    )
    assert completed.status_code == 200
    evidence = completed.json()["episode"]
    assert evidence["raw_gain"] == 50
    assert evidence["status"] == "completed"
    assert episode_client.get("/api/v1/education/episodes/current").json() == {"episode": None}


def test_episode_rejects_knowledge_point_from_other_course(episode_client: TestClient):
    response = episode_client.post(
        "/api/v1/education/episodes",
        json={
            "course_id": "image-recognition",
            "knowledge_point_id": "edu_other_course_m0_kp0",
            "pre_score": 25,
        },
    )
    assert response.status_code == 422
