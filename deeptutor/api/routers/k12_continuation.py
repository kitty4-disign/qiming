"""K12 turn-boundary continuation helpers.

The K12 tutor treats ``ask_user`` as the end of the current teaching turn.
A learner answer therefore belongs to a *new* turn with a fresh agent-loop
budget. Keeping that boundary explicit avoids two failure modes:

* an answer submitted while the previous turn is finalising can be queued on
  the old turn and the follow-up turn id can be lost to the WebSocket;
* a server-created follow-up that omits session context can fall back to
  default language/tools/knowledge bases.

Ordinary chat keeps its existing in-turn ``ask_user`` pause/resume behaviour.
"""

from __future__ import annotations

import asyncio
from typing import Any


_K12_CAPABILITY = "k12_tutor"
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def flatten_k12_reply(
    text: str | None,
    answers: list[dict[str, Any]] | None,
) -> str:
    """Flatten the v2 ask-user reply into the next turn's user message."""
    if answers:
        parts = [
            str(entry.get("text") or "").strip()
            for entry in answers
            if isinstance(entry, dict)
        ]
        parts = [part for part in parts if part]
        if parts:
            return " | ".join(parts)
    return str(text or "").strip()


async def wait_for_turn_terminal(
    runtime: Any,
    turn_id: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval: float = 0.025,
) -> dict[str, Any] | None:
    """Wait until a K12 boundary turn is no longer persisted as running."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, timeout_seconds)
    while True:
        turn = await runtime.store.get_turn(turn_id)
        if turn is None:
            return None
        status = str(turn.get("status") or "").strip()
        if status in _TERMINAL_STATUSES or status != "running":
            return turn
        if loop.time() >= deadline:
            return turn
        await asyncio.sleep(max(0.0, poll_interval))


def _follow_up_payload(
    *,
    session_id: str,
    preferences: dict[str, Any],
    content: str,
) -> dict[str, Any]:
    """Build an explicit follow-up payload from stored K12 session state."""
    payload: dict[str, Any] = {
        "session_id": session_id,
        "capability": _K12_CAPABILITY,
        "content": content or "(skipped)",
        "tools": list(preferences.get("tools") or []),
        "knowledge_bases": list(preferences.get("knowledge_bases") or []),
        "language": str(preferences.get("language") or "en"),
        "config": dict(preferences.get("capability_config") or {}),
    }
    if "education_context" in preferences:
        payload["education_context"] = preferences.get("education_context")
    if "persona" in preferences:
        payload["persona"] = str(preferences.get("persona") or "")
    if preferences.get("llm_selection"):
        payload["llm_selection"] = dict(preferences["llm_selection"])
    return payload


async def continue_k12_reply(
    runtime: Any,
    turn_id: str,
    *,
    text: str | None,
    answers: list[dict[str, Any]] | None,
    timeout_seconds: float = 30.0,
) -> str | bool:
    """Start the learner-answer follow-up and return its concrete turn id."""
    original_turn = await runtime.store.get_turn(turn_id)
    if original_turn is None:
        return False
    if str(original_turn.get("capability") or "") != _K12_CAPABILITY:
        return False

    if str(original_turn.get("status") or "") == "running":
        original_turn = await wait_for_turn_terminal(
            runtime,
            turn_id,
            timeout_seconds=timeout_seconds,
        )
        if original_turn is None:
            return False

    # Do not spawn a lesson from a partially persisted failed/cancelled turn.
    if str(original_turn.get("status") or "") != "completed":
        return False

    session_id = str(original_turn.get("session_id") or "").strip()
    if not session_id:
        return False
    session = await runtime.store.get_session(session_id)
    if session is None:
        return False

    preferences = session.get("preferences") or {}
    payload = _follow_up_payload(
        session_id=session_id,
        preferences=preferences,
        content=flatten_k12_reply(text, answers),
    )
    _, new_turn = await runtime.start_turn(payload)
    return str(new_turn.get("id") or "") or False


__all__ = [
    "continue_k12_reply",
    "flatten_k12_reply",
    "wait_for_turn_terminal",
]
