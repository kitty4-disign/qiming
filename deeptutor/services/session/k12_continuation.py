"""Deterministic K12 turn-boundary continuation.

K12 ``ask_user`` is a hard turn boundary: the learner answer must start a new
turn. This module installs a narrow wrapper around the shared runtime so K12
replies never get stranded on the old turn's reply queue while ordinary chat
keeps its same-turn pause/resume behaviour.
"""

from __future__ import annotations

import asyncio
from types import MethodType
from typing import Any, Awaitable, Callable

_K12_CAPABILITY = "k12_tutor"
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def flatten_k12_reply(
    text: str | None,
    answers: list[dict[str, Any]] | None,
) -> str:
    """Flatten structured ask-user answers into the next turn's user message."""
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
    """Wait for the K12 boundary turn to finish persisting its terminal state."""
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
    """Build an explicit K12 follow-up payload from stored session state."""
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

    # A user can click the card during the tiny window between stream DONE and
    # persisted turn completion. Waiting here removes the race without feeding
    # the answer into the old queue (K12 never consumes that queue at boundary).
    if str(original_turn.get("status") or "") == "running":
        original_turn = await wait_for_turn_terminal(
            runtime,
            turn_id,
            timeout_seconds=timeout_seconds,
        )
        if original_turn is None:
            return False

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
    try:
        _, new_turn = await runtime.start_turn(payload)
    except RuntimeError:
        return False
    return str(new_turn.get("id") or "") or False


def install_k12_continuation(runtime: Any) -> Any:
    """Install K12-aware ``submit_user_reply`` on one runtime instance.

    The public WebSocket already subscribes automatically when
    ``submit_user_reply`` returns a string turn id. We preserve that contract
    and leave non-K12 replies delegated to the original runtime method.
    """
    if getattr(runtime, "_k12_continuation_installed", False):
        return runtime

    original: Callable[..., Awaitable[str | bool]] = runtime.submit_user_reply

    async def _submit_user_reply(
        self: Any,
        turn_id: str,
        text: str | None = None,
        *,
        answers: list[dict[str, Any]] | None = None,
    ) -> str | bool:
        turn = await self.store.get_turn(turn_id)
        if turn is not None and str(turn.get("capability") or "") == _K12_CAPABILITY:
            return await continue_k12_reply(
                self,
                turn_id,
                text=text,
                answers=answers,
            )
        return await original(turn_id, text=text, answers=answers)

    runtime.submit_user_reply = MethodType(_submit_user_reply, runtime)
    runtime._k12_continuation_installed = True
    return runtime


__all__ = [
    "continue_k12_reply",
    "flatten_k12_reply",
    "install_k12_continuation",
    "wait_for_turn_terminal",
]
