from __future__ import annotations

from pathlib import Path

from deeptutor.education.models import StudentProfile
from deeptutor.services.path_service import get_path_service


class EducationProfileService:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or get_path_service().get_settings_file("education_profile")

    def load(self) -> StudentProfile | None:
        path = self.path
        if not path.exists():
            return None
        return StudentProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, profile: StudentProfile) -> StudentProfile:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        temp.replace(path)
        return profile
