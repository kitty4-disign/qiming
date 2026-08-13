"""Public request contracts and config validators for built-in capabilities."""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from deeptutor.agents.math_animator.request_config import (
    MathAnimatorRequestConfig,
    validate_math_animator_request_config,
)
from deeptutor.agents.research.request_config import (
    DeepResearchRequestConfig,
    validate_research_request_config,
)
from deeptutor.education.models import STAGE_GRADE_RANGE, EducationStage

_RUNTIME_ONLY_KEYS = {
    "_persist_user_message",
    "followup_question_context",
    # Per-turn subagent consult budget (composer stepper). Not part of any
    # capability's public config schema; stripped here so it never trips
    # ``extra="forbid"`` (turn_runtime carries it through to the turn config).
    "subagent_consult_budget",
}


class ChatRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeepSolveRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeepQuestionRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["custom", "mimic"] = "custom"
    topic: str = ""
    num_questions: int = Field(default=1, ge=1, le=50)
    difficulty: str = ""
    # Allowed-types whitelist. Empty list means "any type — let the
    # planner pick per question". Frontend sends the user's multi-select.
    question_types: list[str] = Field(default_factory=list)
    # Optional per-type quantity targets. When non-empty, sum must equal
    # ``num_questions`` (frontend keeps them in sync). Empty dict means
    # "no per-type targets — distribute freely across allowed types".
    per_type_counts: dict[str, int] = Field(default_factory=dict)
    paper_path: str = ""
    max_questions: int = Field(default=10, ge=1, le=100)


class VisualizeRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_mode: Literal[
        "auto",
        "svg",
        "chartjs",
        "mermaid",
        "html",
        "manim_video",
        "manim_image",
    ] = "auto"
    # Only meaningful when the routed render_type is manim_video / manim_image
    # (either chosen explicitly or selected by AnalysisAgent in auto mode).
    # Mirrors MathAnimatorRequestConfig defaults so the auto path stays
    # zero-config.
    quality: Literal["low", "medium", "high"] = "medium"
    style_hint: str = Field(default="", max_length=500)


class K12TutorRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    mastery_path_id: str = Field(
        min_length=1, max_length=180, pattern=r"^[A-Za-z0-9_-]+$"
    )
    # ``lesson`` = explain/diagnose; ``quiz`` = pose one question, grade it,
    # update mastery; ``coding`` = scaffolded code practice.  The mode is read
    # by the capability and injected into the tutor guidance so the model
    # follows the right mastery flow without guessing.
    activity_mode: Literal["lesson", "quiz", "coding"] = "lesson"
    # A dashboard launch gets a stable run id (currently the launch timestamp).
    # The following counters are carried in capability_config so the K12
    # turn-boundary continuation persists them automatically across fresh
    # turns. This turns "three quiz questions" from a prompt convention into
    # explicit server-visible state.
    quiz_run_id: str = Field(default="", max_length=80, pattern=r"^[A-Za-z0-9_-]*$")
    quiz_question_count: int = Field(default=3, ge=1, le=10)
    quiz_answered_count: int = Field(default=0, ge=0, le=10)
    quiz_last_answered_turn_id: str = Field(default="", max_length=180)

    @model_validator(mode="after")
    def validate_quiz_state(self) -> "K12TutorRequestConfig":
        if self.quiz_answered_count > self.quiz_question_count:
            raise ValueError("quiz_answered_count cannot exceed quiz_question_count")
        return self


class EducationRequestContext(BaseModel):
    """Per-turn teaching context shared by education-aware capabilities."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stage: EducationStage
    grade: int = Field(ge=1, le=12)
    knowledge_point_id: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_stage_grade(self) -> "EducationRequestContext":
        low, high = STAGE_GRADE_RANGE[self.stage]
        if not low <= self.grade <= high:
            raise ValueError(
                f"grade must be between {low} and {high} for {self.stage.value}"
            )
        return self


def _clean_public_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    if raw_config is None:
        return {}
    if not isinstance(raw_config, dict):
        raise ValueError("Capability config must be an object.")
    cleaned = dict(raw_config)
    for key in _RUNTIME_ONLY_KEYS:
        cleaned.pop(key, None)
    return cleaned


def _validate_model(
    model_type: type[BaseModel],
    raw_config: dict[str, Any] | None,
    *,
    label: str,
) -> BaseModel:
    cleaned = _clean_public_config(raw_config)
    try:
        return model_type.model_validate(cleaned)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValueError(f"Invalid {label} config: {details}") from exc


def validate_chat_request_config(raw_config: dict[str, Any] | None) -> ChatRequestConfig:
    return _validate_model(ChatRequestConfig, raw_config, label="chat")


def validate_deep_solve_request_config(
    raw_config: dict[str, Any] | None,
) -> DeepSolveRequestConfig:
    return _validate_model(DeepSolveRequestConfig, raw_config, label="deep solve")


def validate_deep_question_request_config(
    raw_config: dict[str, Any] | None,
) -> DeepQuestionRequestConfig:
    return _validate_model(DeepQuestionRequestConfig, raw_config, label="deep question")


def validate_visualize_request_config(
    raw_config: dict[str, Any] | None,
) -> VisualizeRequestConfig:
    return _validate_model(VisualizeRequestConfig, raw_config, label="visualize")


def validate_k12_tutor_request_config(
    raw_config: dict[str, Any] | None,
) -> K12TutorRequestConfig:
    return _validate_model(K12TutorRequestConfig, raw_config, label="K12 tutor")


def validate_education_request_context(
    raw_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if raw_context is None:
        return None
    if not isinstance(raw_context, dict):
        raise ValueError("Education context must be an object.")
    try:
        model = EducationRequestContext.model_validate(raw_context)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValueError(f"Invalid education context: {details}") from exc
    return model.model_dump(mode="json", exclude_none=True)


def build_request_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    return model_type.model_json_schema(mode="validation")


CAPABILITY_CONFIG_VALIDATORS: dict[str, Callable[[dict[str, Any] | None], Any]] = {
    "chat": validate_chat_request_config,
    "deep_solve": validate_deep_solve_request_config,
    "deep_question": validate_deep_question_request_config,
    "deep_research": validate_research_request_config,
    "math_animator": validate_math_animator_request_config,
    "k12_tutor": validate_k12_tutor_request_config,
    "visualize": validate_visualize_request_config,
}

CAPABILITY_REQUEST_SCHEMAS: dict[str, dict[str, Any]] = {
    "chat": build_request_schema(ChatRequestConfig),
    "deep_solve": build_request_schema(DeepSolveRequestConfig),
    "deep_question": build_request_schema(DeepQuestionRequestConfig),
    "deep_research": build_request_schema(DeepResearchRequestConfig),
    "math_animator": build_request_schema(MathAnimatorRequestConfig),
    "k12_tutor": build_request_schema(K12TutorRequestConfig),
    "visualize": build_request_schema(VisualizeRequestConfig),
}


def validate_capability_config(
    capability: str, raw_config: dict[str, Any] | None
) -> dict[str, Any]:
    validator = CAPABILITY_CONFIG_VALIDATORS.get(capability)
    if validator is None:
        return _clean_public_config(raw_config)
    model = validator(raw_config)
    if isinstance(model, BaseModel):
        return model.model_dump(exclude_none=True)
    return _clean_public_config(raw_config)


def get_capability_request_schema(capability: str) -> dict[str, Any]:
    return dict(CAPABILITY_REQUEST_SCHEMAS.get(capability, {}))


__all__ = [
    "CAPABILITY_CONFIG_VALIDATORS",
    "CAPABILITY_REQUEST_SCHEMAS",
    "ChatRequestConfig",
    "DeepQuestionRequestConfig",
    "DeepSolveRequestConfig",
    "EducationRequestContext",
    "K12TutorRequestConfig",
    "VisualizeRequestConfig",
    "build_request_schema",
    "get_capability_request_schema",
    "validate_capability_config",
    "validate_chat_request_config",
    "validate_deep_question_request_config",
    "validate_deep_solve_request_config",
    "validate_education_request_context",
    "validate_k12_tutor_request_config",
    "validate_visualize_request_config",
]
