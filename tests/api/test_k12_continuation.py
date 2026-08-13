from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.session.k12_continuation import (
    advance_quiz_state,
    continue_k12_reply,
    flatten_k12_reply,
    install_k12_continuation,
)


class _FakeStore:
    def __init__(
        self,
        *,
        statuses: list[str],
        preferences: dict[str, Any] | None = None,
        capability: str = "k12_tutor",
    ) -> None:
        self.statuses = list(statuses)
        self.preferences = preferences or {}
        self.capability = capability
        self.reads = 0

    async def get_turn(self, turn_id: str) -> dict[str, Any]:
        index = min(self.reads, len(self.statuses) - 1)
        self.reads += 1
        return {
            "id": turn_id,
            "session_id": "session-1",
            "capability": self.capability,
            "status": self.statuses[index],
        }

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return {"id": session_id, "preferences": dict(self.preferences)}


class _FakeRuntime:
    def __init__(self, store: _FakeStore) -> None:
        self.store = store
        self.started_payload: dict[str, Any] | None = None
        self.original_reply_calls: list[tuple[str, str | None, list[dict[str, Any]] | None]] = []

    async def start_turn(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self.started_payload = dict(payload)
        return {"id": "session-1"}, {"id": "turn-2"}

    async def submit_user_reply(
        self,
        turn_id: str,
        text: str | None = None,
        *,
        answers: list[dict[str, Any]] | None = None,
    ) -> str | bool:
        self.original_reply_calls.append((turn_id, text, answers))
        return True


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


def test_quiz_state_advances_once_per_answered_turn() -> None:
    config = {
        "course_id": "course-1",
        "mastery_path_id": "path-1",
        "activity_mode": "quiz",
        "quiz_run_id": "12345",
        "quiz_question_count": 3,
        "quiz_answered_count": 0,
        "quiz_last_answered_turn_id": "",
    }

    first = advance_quiz_state(config, "turn-1")
    duplicate = advance_quiz_state(first, "turn-1")
    second = advance_quiz_state(duplicate, "turn-2")
    third = advance_quiz_state(second, "turn-3")
    capped = advance_quiz_state(third, "turn-4")

    assert first["quiz_answered_count"] == 1
    assert duplicate["quiz_answered_count"] == 1
    assert second["quiz_answered_count"] == 2
    assert third["quiz_answered_count"] == 3
    assert capped["quiz_answered_count"] == 3
    assert capped["quiz_last_answered_turn_id"] == "turn-3"


@pytest.mark.asyncio
async def test_k12_reply_waits_for_terminal_and_preserves_session_context() -> None:
    quiz_config = {
        "course_id": "course-1",
        "mastery_path_id": "path-1",
        "activity_mode": "quiz",
        "quiz_run_id": "12345",
        "quiz_question_count": 3,
        "quiz_answered_count": 0,
        "quiz_last_answered_turn_id": "",
    }
    preferences = {
        "tools": ["code_execution"],
        "knowledge_bases": ["kb-ai-literacy"],
        "language": "zh",
        "capability_config": quiz_config,
        "education_context": {
            "stage": "middle",
            "grade": 8,
            "knowledge_point_id": "kp-1",
        },
        "persona": "Socratic",
        "llm_selection": {"profile_id": "profile-1", "model_id": "model-1"},
    }
    runtime = _FakeRuntime(_FakeStore(statuses=["running", "completed"], preferences=preferences))

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
    assert runtime.started_payload["config"] == {
        **quiz_config,
        "quiz_answered_count": 1,
        "quiz_last_answered_turn_id": "turn-1",
    }
    assert runtime.started_payload["education_context"] == preferences["education_context"]
    assert runtime.started_payload["persona"] == "Socratic"
    assert runtime.started_payload["llm_selection"] == preferences["llm_selection"]


@pytest.mark.asyncio
async def test_duplicate_quiz_card_does_not_start_second_follow_up() -> None:
    preferences = {
        "capability_config": {
            "course_id": "course-1",
            "mastery_path_id": "path-1",
            "activity_mode": "quiz",
            "quiz_question_count": 3,
            "quiz_answered_count": 1,
            "quiz_last_answered_turn_id": "turn-1",
        }
    }
    runtime = _FakeRuntime(_FakeStore(statuses=["completed"], preferences=preferences))

    follow_up = await continue_k12_reply(
        runtime,
        "turn-1",
        text="B",
        answers=None,
        timeout_seconds=0.01,
    )

    assert follow_up is False
    assert runtime.started_payload is None


@pytest.mark.asyncio
async def test_installed_wrapper_returns_new_turn_id_for_k12() -> None:
    runtime = _FakeRuntime(_FakeStore(statuses=["completed"]))
    install_k12_continuation(runtime)

    result = await runtime.submit_user_reply("turn-1", text="B")

    assert result == "turn-2"
    assert runtime.original_reply_calls == []


@pytest.mark.asyncio
async def test_installed_wrapper_delegates_non_k12_reply() -> None:
    runtime = _FakeRuntime(_FakeStore(statuses=["running"], capability="chat"))
    install_k12_continuation(runtime)

    result = await runtime.submit_user_reply("turn-1", text="hello")

    assert result is True
    assert runtime.original_reply_calls == [("turn-1", "hello", None)]


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
