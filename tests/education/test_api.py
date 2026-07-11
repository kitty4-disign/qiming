from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deeptutor.api.routers.education as education_module
from deeptutor.education.profile_service import EducationProfileService


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    service = EducationProfileService(path=tmp_path / "education_profile.json")
    monkeypatch.setattr(education_module, "_profile_service", lambda: service)
    monkeypatch.setattr(education_module, "list_visible_knowledge_bases", lambda: [])
    app = FastAPI()
    app.include_router(education_module.router, prefix="/api/v1/education")
    return TestClient(app)


def save_primary_upper_profile(client: TestClient) -> None:
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


def test_get_profile_returns_null_before_onboarding(client):
    response = client.get("/api/v1/education/profile")
    assert response.status_code == 200
    assert response.json() == {"profile": None}


def test_put_profile_rejects_cross_stage_textbook(client):
    response = client.put(
        "/api/v1/education/profile",
        json={
            "display_name": "小航",
            "stage": "primary_upper",
            "grade": 5,
            "textbook_id": "k12-ai-high",
            "interests": [],
            "preferred_modalities": ["dialogue", "quiz"],
            "learning_goal": "",
        },
    )
    assert response.status_code == 422
    assert "does not belong to stage" in response.json()["detail"]


def test_launch_context_contains_stable_path_and_kb_warning(client):
    save_primary_upper_profile(client)
    response = client.get("/api/v1/education/launch-context/image-recognition")
    assert response.status_code == 200
    body = response.json()
    assert body["mastery_path_id"] == "edu_k12_ai_primary_upper_image_recognition"
    assert body["course"]["id"] == "image-recognition"
    assert body["knowledge_bases"] in ([], ["k12-ai-primary-upper"])
