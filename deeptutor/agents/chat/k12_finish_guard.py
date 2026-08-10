"""K12 guard for premature tool-less AgentLoop finishes.

A generic chat loop is allowed to stop whenever the model emits no tool call.
That is correct for chat, but a K12 mastery turn has a stricter contract: while
mastery is incomplete, it must reach an ``ask_user`` boundary instead of
ending after a feedback sentence. This module patches only that finish seam.
"""

from __future__ import annotations

import json
from typing import Any

_K12_ACTIVITY_MODES = frozenset({"lesson", "quiz", "coding"})


class _K12PrematureFinish(RuntimeError):
    def __init__(self, raw_text: str) -> None:
        super().__init__("k12_premature_toolless_finish")
        self.raw_text = raw_text


def _is_managed_k12_turn(context: Any) -> bool:
    metadata = getattr(context, "metadata", {}) or {}
    return bool(
        metadata.get("ask_user_turn_boundary")
        and str(metadata.get("education_activity_mode") or "") in _K12_ACTIVITY_MODES
    )


def _json_payload(content: Any) -> Any:
    if isinstance(content, (dict, list)):
        return content
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        return None


def _contains_complete_next(value: Any) -> bool:
    if isinstance(value, dict):
        next_value = value.get("next")
        if isinstance(next_value, dict) and str(next_value.get("action") or "") == "complete":
            return True
        return any(_contains_complete_next(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_complete_next(item) for item in value)
    return False


def _contains_grade_result(value: Any) -> bool:
    if isinstance(value, dict):
        # mastery_grade's public result always contains these server-computed
        # fields. This avoids relying on provider-specific role=tool name shape.
        if "is_correct" in value and "knowledge_point_id" in value and "next" in value:
            return True
        return any(_contains_grade_result(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_grade_result(item) for item in value)
    return False


def _tool_payloads(messages: list[dict[str, Any]]) -> list[Any]:
    return [
        payload
        for message in messages
        if message.get("role") == "tool"
        for payload in [_json_payload(message.get("content"))]
        if payload is not None
    ]


def k12_finish_is_allowed(context: Any, messages: list[dict[str, Any]]) -> bool:
    """Whether a managed K12 turn may legitimately finish without ``ask_user``."""
    if not _is_managed_k12_turn(context):
        return True

    metadata = getattr(context, "metadata", {}) or {}
    payloads = _tool_payloads(messages)
    activity_mode = str(metadata.get("education_activity_mode") or "")
    if activity_mode == "quiz" and metadata.get("education_quiz_limit_reached"):
        # Reaching 3/3 means the latest learner answer still has to be graded.
        # Only after a real mastery_grade result may the final summary close.
        return any(_contains_grade_result(payload) for payload in payloads)

    # For lesson/coding (and non-final quiz turns), course completion reported
    # by the deterministic mastery engine is the only tool-less exit besides
    # reaching ask_user, which returns earlier through DispatchOutcome.pause.
    return any(_contains_complete_next(payload) for payload in payloads)


def _continuation_nudge(language: str) -> str:
    if str(language).lower().startswith("zh"):
        return (
            "你刚才尝试在 K12 教学状态仍未结束时直接结束本轮。不要重复上一段反馈。"
            "现在先调用 mastery_status；如果存在待批改答案，先 mastery_grade。只有服务端返回 "
            "next.action=complete 才能直接总结结束；否则继续一个最小教学步骤，并以恰好一个 "
            "ask_user 问题结束当前 turn。"
        )
    return (
        "You attempted to finish this K12 turn before its mastery boundary. Do not repeat the "
        "previous feedback. Call mastery_status now; if an answer is pending, grade it first. "
        "Only next.action=complete may finish directly. Otherwise continue one minimal teaching "
        "step and end the turn with exactly one ask_user question."
    )


def install_k12_finish_guard(agent_loop_module: Any) -> None:
    """Install one bounded K12 retry around ``AgentLoop._finalize_finish``."""
    AgentLoop = agent_loop_module.AgentLoop
    if getattr(AgentLoop, "_k12_finish_guard_installed", False):
        return

    original_run_loop = AgentLoop._run_loop
    original_finalize = AgentLoop._finalize_finish

    async def _guarded_finalize(self: Any, raw_text: str):
        if (
            getattr(self, "_k12_finish_guard_active", False)
            and _is_managed_k12_turn(self.context)
            and not getattr(self, "_k12_finish_guard_bypass", False)
        ):
            raise _K12PrematureFinish(raw_text)
        return await original_finalize(self, raw_text)

    async def _guarded_run_loop(
        self: Any,
        *,
        messages: list[dict[str, Any]],
        state: Any,
        checkpoint_boundary: int,
    ):
        if not _is_managed_k12_turn(self.context):
            return await original_run_loop(
                self,
                messages=messages,
                state=state,
                checkpoint_boundary=checkpoint_boundary,
            )

        self._k12_finish_guard_active = True
        retry_used = False
        try:
            while True:
                try:
                    return await original_run_loop(
                        self,
                        messages=messages,
                        state=state,
                        checkpoint_boundary=checkpoint_boundary,
                    )
                except _K12PrematureFinish as exc:
                    if k12_finish_is_allowed(self.context, messages) or retry_used:
                        # Bounded escape hatch: never create an infinite agent
                        # loop if a provider refuses tools twice in a row.
                        self._k12_finish_guard_bypass = True
                        try:
                            return await original_finalize(self, exc.raw_text)
                        finally:
                            self._k12_finish_guard_bypass = False

                    retry_used = True
                    cleaned = self._sanitize_user_facing_text(self._clean(exc.raw_text))
                    if cleaned:
                        messages.append({"role": "assistant", "content": cleaned})
                    messages.append(
                        {
                            "role": "user",
                            "content": _continuation_nudge(getattr(self.context, "language", "en")),
                        }
                    )
        finally:
            self._k12_finish_guard_active = False

    AgentLoop._finalize_finish = _guarded_finalize
    AgentLoop._run_loop = _guarded_run_loop
    AgentLoop._k12_finish_guard_installed = True


__all__ = ["install_k12_finish_guard", "k12_finish_is_allowed"]
