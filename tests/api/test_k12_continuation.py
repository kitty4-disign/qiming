from __future__ import annotations

from typing import Any

import pytest

from deeptutor.api.routers.k12_continuation import (
    continue_k12_reply,
    flatten_k12_reply,
)


class _FakeStore:
    def __init__(
        self,
        *,
        statuses: list[str],
        preferences: dict[str, Any] | None = None,
    ) -> None:
        self.statuses = list(statuses)
        self.preferences = preferences or {}
        self.reads = 0

    async def get_turn(self, turn_id: str) -> dict[str, Any]:
        index = min(self.reads, len(self.statuses) - 1)
        self.reads += 1
        return {
            "id": turn_id,
            "session_id": "session-1",
            "capability": "k12_tutor",
            "status": self.statuses[index],
        }

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return {"id": session_id, "preferences": dict(self.preferences)}


class _FakeRuntime:
    def __init__(self, store: _FakeStore) -> None:
        self.store = store
        self.started_payload: dict[str, Any] | None = None

    async def start_turn(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self.started_payload = dict(payload)
        return {"id": "session-1"}, {"id": "turn-2"}


def test_flatten_k12_reply_prefers_structured_answers() -> None:
    assert (
        flatten_k12_reply(
            "legacy",
            [
                {"questionId": "q1", "text": "B"},
                {"questionId": "q2", "text": "because pixels form a matrix"},
            ],
        )
        == "B | because pixels form a matrix"
    )


@pytest.mark.asyncio
async def test_k12_reply_waits_for_terminal_and_preserves_session_context() -> None:
    preferences = {
        "tools": ["code_execution"],
        "knowledge_bases": ["kb-ai-literacy"],
        "language": "zh",
        "capability_config": {
            "course_id": "course-1",
            "mastery_path_id": "path-1",
            "activity_mode": "quiz",
        },
        "education_context": {
            "stage": "junior_high",
            "grade": "8",
            "knowledge_point_id": "kp-1",
        },
        "persona": "Socratic",
        "llm_selection": {"profile_id": "profile-1", "model_id": "model-1"},
    }
    runtime = _FakeRuntime(
        _FakeStore(statuses=["running", "completed"], preferences=preferences)
    )

    follow_up = await continue_k12_reply(
        runtime,
        "turn-1",
        text="B",
        answers=None,
        timeout_seconds=0.1,
    )

    assert follow_up == "turn-2"
    assert runtime.started_payload is not None
    assert runtime.started_payload["session_id"] == "session-1"
    assert runtime.started_payload["capability"] == "k12_tutor"
    assert runtime.started_payload["content"] == "B"
    assert runtime.started_payload["tools"] == ["code_execution"]
    assert runtime.started_payload["knowledge_bases"] == ["kb-ai-literacy"]
    assert runtime.started_payload["language"] == "zh"
    assert runtime.started_payload["config"] == preferences["capability_config"]
    assert runtime.started_payload["education_context"] == preferences["education_context"]
    assert runtime.started_payload["persona"] == "Socratic"
    assert runtime.started_payload["llm_selection"] == preferences["llm_selection"]


@pytest.mark.asyncio
async def test_failed_k12_turn_does_not_spawn_follow_up() -> None:
    runtime = _FakeRuntime(_FakeStore(statuses=["failed"]))

    follow_up = await continue_k12_reply(
        runtime,
        "turn-1",
        text="B",
        answers=None,
        timeout_seconds=0.01,
    )

    assert follow_up is False
    assert runtime.started_payload is None
