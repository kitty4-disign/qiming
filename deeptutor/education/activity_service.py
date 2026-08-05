from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from deeptutor.education.activity_models import ActivityCompletion, LearningEvent
from deeptutor.services.path_service import get_path_service

_MAX_EVENTS = 500


class EducationActivityService:
    """Persist learning activity events for the current user.

    Storage is a single JSON file per user (``settings/education_events.json``)
    so writes are atomic and the data is trivially inspectable.  Only the
    minimum evidence is kept — no dialogue content, names, contacts or keys.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or get_path_service().get_settings_file("education_events")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_recent(self, *, limit: int = 50) -> list[LearningEvent]:
        data = self._load()
        events = data.get("events", [])
        return [LearningEvent.model_validate(item) for item in events[:limit]]

    def list_for_course(self, course_id: str, *, limit: int = 50) -> list[LearningEvent]:
        data = self._load()
        events = [
            LearningEvent.model_validate(item)
            for item in data.get("events", [])
            if item.get("course_id") == course_id
        ]
        return events[:limit]

    def record(self, completion: ActivityCompletion) -> LearningEvent:
        """Record an event, enforcing idempotency and the 500-event cap."""
        data = self._load()
        events: list[dict[str, Any]] = data.get("events", [])
        idempotency_key = completion.idempotency_key

        # Idempotency: if a completed event with the same key exists, return it.
        if idempotency_key:
            for existing in events:
                if (
                    existing.get("idempotency_key") == idempotency_key
                    and existing.get("event_type") == "completed"
                    and existing.get("course_id") == completion.course_id
                ):
                    return LearningEvent.model_validate(existing)

        event = LearningEvent(
            id=f"evt_{uuid.uuid4().hex[:16]}",
            course_id=completion.course_id,
            mastery_path_id=completion.mastery_path_id,
            activity=completion.activity,
            event_type=completion.event_type,
            knowledge_point_id=completion.knowledge_point_id,
            score=completion.score,
            duration_seconds=completion.duration_seconds,
            idempotency_key=idempotency_key,
            created_at=time.time(),
        )
        events.insert(0, event.model_dump(mode="json"))
        # Enforce the retention cap.
        if len(events) > _MAX_EVENTS:
            events = events[:_MAX_EVENTS]
        self._save({"events": events})
        return event

    def summarize(self, course_id: str | None = None) -> dict[str, Any]:
        """Return a compact summary suitable for the dashboard and gamification."""
        if course_id:
            events = self.list_for_course(course_id, limit=_MAX_EVENTS)
        else:
            events = self.list_recent(limit=_MAX_EVENTS)
        completed = [e for e in events if e.event_type == "completed"]
        quiz_events = [e for e in completed if e.activity == "quiz"]
        correct_quizzes = [e for e in quiz_events if (e.score or 0.0) >= 0.7]
        last_event_at = events[0].created_at if events else 0.0
        return {
            "total_events": len(events),
            "completed_count": len(completed),
            "quiz_completed": len(quiz_events),
            "quiz_correct": len(correct_quizzes),
            "last_event_at": last_event_at,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        path = self.path
        if not path.exists():
            return {"events": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"events": []}

    def _save(self, data: dict[str, Any]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp file in same dir, then os.replace.
        fd, tmp_name = tempfile.mkstemp(
            prefix=".education_events_", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_name, path)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise


__all__ = ["EducationActivityService"]
