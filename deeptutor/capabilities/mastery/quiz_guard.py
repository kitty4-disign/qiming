"""Server-side guard for bounded K12 quiz runs."""

from __future__ import annotations

from typing import Any

from deeptutor.core.tool_protocol import ToolResult


def install_mastery_quiz_guard() -> None:
    """Patch ``MasteryQuizTool.execute`` once with a private server gate.

    The gate flag is injected only by :class:`MasteryLoopCapability`; it is not
    part of the model-visible tool schema. Keeping the check inside tool
    execution means normal dispatch converts the refusal into an ordinary tool
    result rather than allowing an extra pending question to be persisted.
    """
    from deeptutor.capabilities.mastery.tools import MasteryQuizTool

    if getattr(MasteryQuizTool, "_k12_quiz_guard_installed", False):
        return

    original_execute = MasteryQuizTool.execute

    async def _guarded_execute(self: Any, **kwargs: Any) -> ToolResult:
        if bool(kwargs.pop("_quiz_question_limit_reached", False)):
            total = int(kwargs.pop("_quiz_question_count", 0) or 0)
            label = str(total) if total > 0 else "configured"
            return ToolResult(
                content=(
                    f"Quiz question limit reached ({label}). Do not register another "
                    "mastery question. Give feedback and the quiz summary instead."
                ),
                success=False,
                metadata={
                    "mastery_quiz": {
                        "status": "question_limit_reached",
                        "question_count": total,
                    }
                },
            )
        kwargs.pop("_quiz_question_count", None)
        return await original_execute(self, **kwargs)

    MasteryQuizTool.execute = _guarded_execute
    MasteryQuizTool._k12_quiz_guard_installed = True


__all__ = ["install_mastery_quiz_guard"]
