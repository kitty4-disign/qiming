"""Mastery path loop capability."""

from deeptutor.capabilities.mastery.loop import MasteryLoopCapability
from deeptutor.capabilities.mastery.quiz_guard import install_mastery_quiz_guard
from deeptutor.capabilities.mastery.tools import MASTERY_TOOL_NAMES, MASTERY_TOOL_TYPES

install_mastery_quiz_guard()

__all__ = ["MASTERY_TOOL_NAMES", "MASTERY_TOOL_TYPES", "MasteryLoopCapability"]
