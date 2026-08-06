"""K12 coding lab models (M3 §8.1).

Coding tasks are seeded from a small YAML fixture so the first high-school
flagship task (2D array → image features → nearest-centroid binary
classification) ships in-repo, auditable and offline-friendly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deeptutor.education.models import EducationStage

CodingLanguage = Literal["python", "c", "cpp"]


class TestCase(BaseModel):
    """A single test case. Hidden tests are never returned to the frontend."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    stdin: str = Field(default="", max_length=4000)
    expected_stdout: str = Field(min_length=1, max_length=4000)
    is_hidden: bool = False


class CodingTask(BaseModel):
    """A coding practice task bound to a course and stage."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=80)
    course_id: str = Field(min_length=1, max_length=80)
    stage: EducationStage
    title: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=4000)
    starter_code: str = Field(min_length=1, max_length=8000)
    allowed_languages: list[CodingLanguage] = Field(default_factory=lambda: ["python"])
    visible_tests: list[TestCase] = Field(default_factory=list, max_length=20)
    hidden_tests: list[TestCase] = Field(default_factory=list, max_length=20)
    hints: list[str] = Field(default_factory=list, max_length=6)


class CodeRunRequest(BaseModel):
    """Payload accepted by ``POST /api/v1/education/code/run``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_id: str = Field(min_length=1, max_length=80)
    task_id: str = Field(min_length=1, max_length=80)
    language: CodingLanguage = "python"
    source_code: str = Field(min_length=1, max_length=12000)
    stdin: str = Field(default="", max_length=4000)


class TestCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    passed: bool
    # stdout/stderr are only returned for visible tests; hidden tests return
    # only pass/fail so the student cannot harvest the expected output.
    stdout: str = ""
    expected: str = ""


class CodeRunResult(BaseModel):
    """Result of a single code run. Hidden test expected outputs are stripped."""

    model_config = ConfigDict(extra="forbid")

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    language: CodingLanguage
    visible_results: list[TestCaseResult]
    hidden_passed: int
    hidden_total: int
    all_visible_passed: bool
    all_hidden_passed: bool


__all__ = [
    "CodeRunRequest",
    "CodeRunResult",
    "CodingLanguage",
    "CodingTask",
    "TestCase",
    "TestCaseResult",
]
