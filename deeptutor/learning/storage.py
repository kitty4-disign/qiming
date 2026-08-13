from __future__ import annotations

import json
from pathlib import Path
import threading
import time
import uuid

from deeptutor.learning.models import LearningProgress
from deeptutor.services.path_service import get_path_service

# Module-level lock serializes the compare + write critical section across all
# LearningStore instances in this process. The persisted version check below is
# what prevents two independently loaded progress objects from silently
# overwriting one another.
_cas_lock = threading.Lock()


class ConcurrentLearningUpdateError(RuntimeError):
    """Raised when a stale LearningProgress tries to overwrite newer state."""


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{uuid.uuid4().hex}")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except BaseException:
        # Don't leave an orphaned temp file behind on write/replace failure.
        tmp.unlink(missing_ok=True)
        raise


class LearningStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or (get_path_service().get_workspace_dir() / "learning")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, book_id: str) -> Path:
        if "/" in book_id or "\\" in book_id or ".." in book_id or ":" in book_id:
            raise ValueError(f"Invalid book_id: {book_id!r}")
        return self._root / f"{book_id}.json"

    def save(self, progress: LearningProgress) -> None:
        path = self._path(progress.book_id)
        with _cas_lock:
            if path.exists():
                stored_data = json.loads(path.read_text(encoding="utf-8"))
                stored_version = int(stored_data.get("version", 0) or 0)
                if stored_version != progress.version:
                    raise ConcurrentLearningUpdateError(
                        "Learning progress changed concurrently "
                        f"(book_id={progress.book_id!r}, expected_version={progress.version}, "
                        f"stored_version={stored_version}). Reload before retrying."
                    )
            elif progress.version != 0:
                # A non-zero in-memory version whose file disappeared is stale
                # too; recreating it would resurrect deleted/rotated state.
                raise ConcurrentLearningUpdateError(
                    "Learning progress storage changed concurrently "
                    f"(book_id={progress.book_id!r}, expected_version={progress.version}, "
                    "stored_version=missing). Reload before retrying."
                )

            progress.updated_at = time.time()
            progress.version += 1
            data = progress.model_dump(mode="json")
            text = json.dumps(data, ensure_ascii=False, indent=2)
            _atomic_write_text(path, text)

    def load(self, book_id: str) -> LearningProgress | None:
        path = self._path(book_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return LearningProgress.model_validate(data)

    def delete(self, book_id: str) -> None:
        with _cas_lock:
            path = self._path(book_id)
            if path.exists():
                path.unlink()

    def exists(self, book_id: str) -> bool:
        return self._path(book_id).exists()

    def list_all(self) -> list[str]:
        """Return all book_ids that have stored progress."""
        return sorted(p.stem for p in self._root.glob("*.json") if not p.name.startswith("."))


__all__ = ["LearningStore", "ConcurrentLearningUpdateError"]
