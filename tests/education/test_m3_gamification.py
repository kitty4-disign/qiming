"""M3 §8.2 gamification acceptance tests.

Gamification must be pure: same inputs always produce same outputs. Refresh
never inflates XP or badges because nothing is stored — it is recomputed from
mastery + events on every call. No XP deduction, no leaderboard, no gacha.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from deeptutor.education.activity_models import LearningEvent
from deeptutor.education.gamification import (
    XP_BASE_PER_COMPLETION,
    XP_BONUS_FIRST_CORRECT,
    XP_BONUS_MASTERY_GATE,
    compute_gamification,
)
from deeptutor.education.mastery_seed import ensure_course_mastery_path
from deeptutor.education.catalog import load_catalog
from deeptutor.education.models import EducationStage, StudentProfile
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore


def _profile() -> StudentProfile:
    return StudentProfile(
        display_name="小航",
        stage=EducationStage.HIGH,
        grade=11,
        textbook_id="k12-ai-high",
        interests=["机器人"],
        preferred_modalities=["coding", "dialogue"],
        learning_goal="理解图像分类",
    )


def _event(
    event_id: str,
    *,
    activity: str = "lesson",
    event_type: str = "completed",
    kp_id: str = "",
    score: float | None = None,
    created_at: float | None = None,
) -> LearningEvent:
    return LearningEvent(
        id=event_id,
        course_id="python-image-classifier",
        mastery_path_id="edu_k12_ai_high_python_image_classifier",
        activity=activity,  # type: ignore[arg-type]
        event_type=event_type,  # type: ignore[arg-type]
        knowledge_point_id=kp_id,
        score=score,
        duration_seconds=60,
        idempotency_key=f"key-{event_id}",
        created_at=created_at if created_at is not None else time.time(),
    )


@pytest.fixture
def progress(tmp_path: Path):
    catalog = load_catalog()
    textbook = next(t for t in catalog.textbooks if t.id == "k12-ai-high")
    course = next(c for c in textbook.courses if c.id == "python-image-classifier")
    learning = LearningService(LearningStore(root=tmp_path / "learning"))
    return ensure_course_mastery_path(course, textbook_id=textbook.id, service=learning)


def test_empty_progress_and_events_yields_zero_state(progress):
    summary = compute_gamification(progress, [])
    assert summary.xp_total == 0
    assert summary.level == 1
    assert summary.current_streak_days == 0
    assert summary.badges == []


def test_completion_grants_base_xp(progress):
    events = [_event("e1", activity="lesson")]
    summary = compute_gamification(progress, events)
    assert summary.xp_total == XP_BASE_PER_COMPLETION


def test_first_correct_quiz_grants_bonus(progress):
    events = [
        _event("e1", activity="quiz", kp_id="kp_1", score=1.0),
    ]
    summary = compute_gamification(progress, events)
    assert summary.xp_total == XP_BASE_PER_COMPLETION + XP_BONUS_FIRST_CORRECT


def test_repeated_correct_same_kp_does_not_double_bonus(progress):
    events = [
        _event("e1", activity="quiz", kp_id="kp_1", score=1.0),
        _event("e2", activity="quiz", kp_id="kp_1", score=1.0),
    ]
    summary = compute_gamification(progress, events)
    # Two completions + one first-correct bonus (not two).
    assert summary.xp_total == 2 * XP_BASE_PER_COMPLETION + XP_BONUS_FIRST_CORRECT


def test_wrong_answer_never_deducts_xp(progress):
    events = [
        _event("e1", activity="quiz", kp_id="kp_1", score=0.0),
    ]
    summary = compute_gamification(progress, events)
    # Wrong answer still grants base XP for completing; no bonus, no deduction.
    assert summary.xp_total == XP_BASE_PER_COMPLETION


def test_mastery_gate_grants_bonus(progress):
    kp_id = progress.modules[0].knowledge_points[0].id
    progress.mastery_levels[kp_id] = 0.8
    events = [_event("e1", activity="quiz", kp_id=kp_id, score=1.0)]
    summary = compute_gamification(progress, events)
    assert summary.xp_total == XP_BASE_PER_COMPLETION + XP_BONUS_FIRST_CORRECT + XP_BONUS_MASTERY_GATE


def test_same_inputs_produce_same_outputs(progress):
    events = [_event("e1"), _event("e2", activity="quiz", kp_id="kp_1", score=1.0)]
    now = 1_000_000_000.0
    s1 = compute_gamification(progress, events, now=now)
    s2 = compute_gamification(progress, events, now=now)
    assert s1 == s2


def test_refresh_does_not_inflate_xp(progress):
    """Calling compute_gamification twice with the same events must yield the
    same XP — refresh never inflates."""
    events = [_event("e1", activity="quiz", kp_id="kp_1", score=1.0)]
    s1 = compute_gamification(progress, events)
    s2 = compute_gamification(progress, events)
    assert s1.xp_total == s2.xp_total
    assert s1.badges == s2.badges


def test_streak_counts_consecutive_days(progress):
    now = 1_000_000_000.0
    day = 86400.0
    events = [
        _event("e1", created_at=now - 2 * day),
        _event("e2", created_at=now - 1 * day),
        _event("e3", created_at=now),
    ]
    summary = compute_gamification(progress, events, now=now)
    assert summary.current_streak_days == 3


def test_streak_resets_after_grace_gap(progress):
    now = 1_000_000_000.0
    day = 86400.0
    events = [
        _event("e1", created_at=now - 5 * day),  # too long ago
        _event("e2", created_at=now),
    ]
    summary = compute_gamification(progress, events, now=now)
    assert summary.current_streak_days == 1


def test_badges_earned(progress):
    # Complete one activity → first_steps badge.
    events = [_event("e1")]
    summary = compute_gamification(progress, events)
    assert "first_steps" in summary.badges


def test_quiz_explorer_badge_after_three_quizzes(progress):
    events = [
        _event("e1", activity="quiz"),
        _event("e2", activity="quiz"),
        _event("e3", activity="quiz"),
    ]
    summary = compute_gamification(progress, events)
    assert "quiz_explorer" in summary.badges


def test_first_mastery_badge(progress):
    kp_id = progress.modules[0].knowledge_points[0].id
    progress.mastery_levels[kp_id] = 0.8
    summary = compute_gamification(progress, [])
    assert "first_mastery" in summary.badges


def test_next_badge_progress_returned(progress):
    summary = compute_gamification(progress, [])
    # With no activity, next badge should be first_steps.
    assert summary.next_badge_progress.get("badge") == "first_steps"
