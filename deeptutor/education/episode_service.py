from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from deeptutor.education.episode_models import LearningEpisode
from deeptutor.services.path_service import get_path_service

_MAX_EPISODES = 200
_WRITE_LOCK = threading.Lock()


class EpisodeConflictError(ValueError):
    pass


class LearningEpisodeService:
    """Persist learning episodes in the current user's scoped settings."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or get_path_service().get_settings_file("education_episodes")

    def create(
        self,
        *,
        course_id: str,
        mastery_path_id: str,
        knowledge_point_id: str,
        knowledge_point_name: str,
        stage,
        pre_score: float,
        initial_misconceptions: list[str],
        mastery_before: float,
    ) -> LearningEpisode:
        episode = LearningEpisode(
            episode_id=f"ep_{uuid.uuid4().hex[:16]}",
            course_id=course_id,
            mastery_path_id=mastery_path_id,
            knowledge_point_id=knowledge_point_id,
            knowledge_point_name=knowledge_point_name,
            stage=stage,
            pre_score=pre_score,
            initial_misconceptions=initial_misconceptions,
            mastery_before=mastery_before,
        )
        with _WRITE_LOCK:
            data = self._load()
            episodes = data.get("episodes", [])
            episodes.insert(0, episode.model_dump(mode="json"))
            self._save({"episodes": episodes[:_MAX_EPISODES]})
        return episode

    def get(self, episode_id: str) -> LearningEpisode | None:
        for item in self._load().get("episodes", []):
            if item.get("episode_id") == episode_id:
                return LearningEpisode.model_validate(item)
        return None

    def current(self, *, course_id: str | None = None) -> LearningEpisode | None:
        for item in self._load().get("episodes", []):
            if item.get("status") != "active":
                continue
            if course_id and item.get("course_id") != course_id:
                continue
            return LearningEpisode.model_validate(item)
        return None

    def list_recent(self, *, course_id: str | None = None, limit: int = 20) -> list[LearningEpisode]:
        items = self._load().get("episodes", [])
        if course_id:
            items = [item for item in items if item.get("course_id") == course_id]
        return [LearningEpisode.model_validate(item) for item in items[:limit]]

    def complete(self, episode_id: str, *, mastery_after: float, **updates: Any) -> LearningEpisode:
        with _WRITE_LOCK:
            data = self._load()
            episodes = data.get("episodes", [])
            for index, item in enumerate(episodes):
                if item.get("episode_id") != episode_id:
                    continue
                episode = LearningEpisode.model_validate(item)
                if episode.status != "active":
                    raise EpisodeConflictError("episode_not_active")
                episode = episode.model_copy(
                    update={
                        **updates,
                        "mastery_after": mastery_after,
                        "status": "completed",
                        "ended_at": time.time(),
                    }
                )
                episode = LearningEpisode.model_validate(episode.model_dump())
                episodes[index] = episode.model_dump(mode="json")
                self._save({"episodes": episodes})
                return episode
        raise KeyError(episode_id)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"episodes": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"episodes": []}

    def _save(self, data: dict[str, Any]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".education_episodes_", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temp_name, path)
        except Exception:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            raise


__all__ = ["EpisodeConflictError", "LearningEpisodeService"]
