"""Healthy gamification (M3 §8.2).

Pure functions only — same inputs always produce same outputs. All thresholds
are centralised here and tested, never scattered to the frontend. Gamification
data is *derived* from real activity + mastery records, never a competing
grading system: there is no XP deduction for wrong answers, no leaderboard,
no gacha, no infinite reward animation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from deeptutor.education.activity_models import LearningEvent
from deeptutor.learning.models import LearningProgress

# ── Thresholds (centralised, tested) ────────────────────────────────────────

XP_BASE_PER_COMPLETION = 10
XP_BONUS_FIRST_CORRECT = 15
XP_BONUS_MASTERY_GATE = 50

# Level curve: level n requires cumulative XP = 100 * n * (n+1) / 2.
# L1=100, L2=300, L3=600, L4=1000, ... gentle, no steep cliffs.
_LEVEL_BASE = 100

# Streak is computed from completed events' created_at timestamps, not stored.
# A streak day is a calendar day (in the user's tz) with >=1 completion.
_STREAK_GRACE_HOURS = 36  # allow overnight gap without resetting streak

# Mastery gate: a KP counts as "mastered" at or above this level.
_MASTERY_THRESHOLD = 0.7

# Badges are defined by deterministic predicates, not random rewards.
@dataclass(frozen=True)
class BadgeSpec:
    code: str
    name_zh: str
    description_zh: str
    # Predicate: (progress, events, derived) -> bool
    check: callable  # type: ignore[type-arg]


@dataclass(frozen=True)
class GamificationSummary:
    """Derived gamification state — pure function of progress + events."""

    xp_total: int
    level: int
    xp_into_level: int
    xp_for_next_level: int
    current_streak_days: int
    badges: list[str]
    next_badge_progress: dict[str, str | int | float]


# ── Badge definitions ──────────────────────────────────────────────────────

def _badge_first_steps(progress: LearningProgress, events: list[LearningEvent], derived: GamificationSummary) -> bool:
    """Complete at least one learning activity."""
    return any(e.event_type == "completed" for e in events)


def _badge_quiz_explorer(progress: LearningProgress, events: list[LearningEvent], derived: GamificationSummary) -> bool:
    """Complete at least 3 quiz activities."""
    return sum(1 for e in events if e.event_type == "completed" and e.activity == "quiz") >= 3


def _badge_first_mastery(progress: LearningProgress, events: list[LearningEvent], derived: GamificationSummary) -> bool:
    """Reach mastery gate on at least one knowledge point."""
    return any(level >= _MASTERY_THRESHOLD for level in progress.mastery_levels.values())


def _badge_streak_3(progress: LearningProgress, events: list[LearningEvent], derived: GamificationSummary) -> bool:
    """Maintain a 3-day learning streak."""
    return derived.current_streak_days >= 3


def _badge_half_mastered(progress: LearningProgress, events: list[LearningEvent], derived: GamificationSummary) -> bool:
    """Master at least half of all knowledge points in the course."""
    kp_ids = [kp.id for m in progress.modules for kp in m.knowledge_points]
    if not kp_ids:
        return False
    mastered = sum(1 for kp_id in kp_ids if progress.mastery_levels.get(kp_id, 0.0) >= _MASTERY_THRESHOLD)
    return mastered >= len(kp_ids) / 2


_BADGES: list[BadgeSpec] = [
    BadgeSpec("first_steps", "初学者", "完成第一次学习活动", _badge_first_steps),
    BadgeSpec("quiz_explorer", "测验探索者", "完成 3 次趣味测验", _badge_quiz_explorer),
    BadgeSpec("first_mastery", "首个掌握", "第一个知识点达到掌握标准", _badge_first_mastery),
    BadgeSpec("streak_3", "连续学习", "连续 3 天学习", _badge_streak_3),
    BadgeSpec("half_mastered", "过半掌握", "掌握一半以上知识点", _badge_half_mastered),
]


# ── XP calculation ──────────────────────────────────────────────────────────

def _xp_from_events(events: list[LearningEvent]) -> int:
    """Compute total XP from learning events.

    Rules (M3 §8.2):
    - Completed activity: base XP (no XP for launched/abandoned).
    - First correct quiz per KP: bonus XP.
    - KP reaching mastery gate: bonus XP (once per KP).
    - Wrong answers never deduct XP.
    """
    xp = 0
    seen_correct_kps: set[str] = set()
    for event in events:
        if event.event_type != "completed":
            continue
        xp += XP_BASE_PER_COMPLETION
        if event.activity == "quiz" and event.score is not None and event.score >= 1.0:
            if event.knowledge_point_id and event.knowledge_point_id not in seen_correct_kps:
                xp += XP_BONUS_FIRST_CORRECT
                seen_correct_kps.add(event.knowledge_point_id)
    return xp


def _xp_from_mastery(progress: LearningProgress) -> int:
    """Bonus XP for each KP that crossed the mastery gate."""
    return sum(
        XP_BONUS_MASTERY_GATE
        for level in progress.mastery_levels.values()
        if level >= _MASTERY_THRESHOLD
    )


def _level_from_xp(xp: int) -> tuple[int, int, int]:
    """Return (level, xp_into_level, xp_for_next_level)."""
    level = 0
    remaining = xp
    while remaining >= _LEVEL_BASE * (level + 1):
        remaining -= _LEVEL_BASE * (level + 1)
        level += 1
    needed = _LEVEL_BASE * (level + 1)
    return level + 1, remaining, needed


# ── Streak calculation ──────────────────────────────────────────────────────

def _streak_from_events(events: list[LearningEvent], now: float) -> int:
    """Current streak in days, derived from completed events.

    A streak day = a calendar day with >=1 completed event. The streak counts
    consecutive days up to ``now``. A gap of more than _STREAK_GRACE_HOURS
    resets the streak to 0 (grace period covers overnight).
    """
    completed_days: set[float] = set()
    for event in events:
        if event.event_type != "completed":
            continue
        completed_days.add(int(event.created_at // 86400))

    if not completed_days:
        return 0

    today = int(now // 86400)
    streak = 0
    day = today
    # Allow today or yesterday as the streak anchor (grace period).
    if today not in completed_days and (today - 1) not in completed_days:
        # Check if the most recent activity is within grace period.
        last_day = max(completed_days)
        if (today - last_day) * 24 > _STREAK_GRACE_HOURS:
            return 0
        day = last_day

    while day in completed_days:
        streak += 1
        day -= 1
    return streak


# ── Main entry point ────────────────────────────────────────────────────────

def compute_gamification(
    progress: LearningProgress,
    events: list[LearningEvent],
    *,
    now: float | None = None,
) -> GamificationSummary:
    """Derive the full gamification state from real learning records.

    Pure function: same inputs → same outputs. Safe to call on every page
    load; refresh never inflates XP or badges because nothing is stored.
    """
    if now is None:
        now = time.time()

    xp_total = _xp_from_events(events) + _xp_from_mastery(progress)
    level, xp_into_level, xp_for_next_level = _level_from_xp(xp_total)
    streak = _streak_from_events(events, now)

    # Build a preliminary summary for badge predicates that depend on it.
    preliminary = GamificationSummary(
        xp_total=xp_total,
        level=level,
        xp_into_level=xp_into_level,
        xp_for_next_level=xp_for_next_level,
        current_streak_days=streak,
        badges=[],
        next_badge_progress={},
    )

    earned: list[str] = []
    for spec in _BADGES:
        if spec.check(progress, events, preliminary):
            earned.append(spec.code)

    # Next badge progress: first unearned badge, with a progress hint.
    next_badge: dict[str, str | int | float] = {}
    for spec in _BADGES:
        if spec.code not in earned:
            if spec.code == "first_steps":
                next_badge = {"badge": spec.code, "remaining": 1, "name_zh": spec.name_zh}
            elif spec.code == "quiz_explorer":
                completed_quizzes = sum(1 for e in events if e.event_type == "completed" and e.activity == "quiz")
                next_badge = {"badge": spec.code, "current": completed_quizzes, "target": 3, "name_zh": spec.name_zh}
            elif spec.code == "first_mastery":
                mastered = sum(1 for v in progress.mastery_levels.values() if v >= _MASTERY_THRESHOLD)
                next_badge = {"badge": spec.code, "current": mastered, "target": 1, "name_zh": spec.name_zh}
            elif spec.code == "streak_3":
                next_badge = {"badge": spec.code, "current": streak, "target": 3, "name_zh": spec.name_zh}
            elif spec.code == "half_mastered":
                kp_ids = [kp.id for m in progress.modules for kp in m.knowledge_points]
                mastered = sum(1 for kp_id in kp_ids if progress.mastery_levels.get(kp_id, 0.0) >= _MASTERY_THRESHOLD)
                target = max(1, len(kp_ids) // 2)
                next_badge = {"badge": spec.code, "current": mastered, "target": target, "name_zh": spec.name_zh}
            break

    return GamificationSummary(
        xp_total=xp_total,
        level=level,
        xp_into_level=xp_into_level,
        xp_for_next_level=xp_for_next_level,
        current_streak_days=streak,
        badges=earned,
        next_badge_progress=next_badge,
    )


__all__ = [
    "BadgeSpec",
    "GamificationSummary",
    "XP_BASE_PER_COMPLETION",
    "XP_BONUS_FIRST_CORRECT",
    "XP_BONUS_MASTERY_GATE",
    "compute_gamification",
]
