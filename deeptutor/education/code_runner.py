"""K12 coding lab runner (M3 §8.1).

Runs student code in the existing sandbox service — never in the FastAPI
process — and evaluates it against visible + hidden tests. Hidden test
expected outputs are stripped from the response.
"""

from __future__ import annotations

import base64

from deeptutor.education.coding_models import (
    CodeRunRequest,
    CodeRunResult,
    CodingTask,
    TestCaseResult,
)
from deeptutor.education.coding_tasks import get_coding_task
from deeptutor.services.sandbox import (
    ExecRequest,
    ExecResult,
    ResourceLimits,
    SandboxService,
    get_sandbox_service,
)

# Hard ceilings a student cannot exceed regardless of the task config.
_MAX_SOURCE_CHARS = 12000
_MAX_STDIN_CHARS = 4000
_MAX_TIMEOUT_S = 15
_MAX_OUTPUT_CHARS = 8000

# Detect obvious sandbox-escape attempts in source code. This is a defence in
# depth — the sandbox itself enforces isolation; this layer just refuses to
# ship obviously hostile code so the student gets a clear error instead of an
# opaque backend rejection.
_FORBIDDEN_IMPORTS = (
    "import socket",
    "import subprocess",
    "import os",
    "import ctypes",
    "from socket",
    "from subprocess",
    "from os",
    "from ctypes",
    "import urllib",
    "import requests",
    "import shutil",
    "import pathlib",
    "__import__",
)


class CodeRunError(Exception):
    """Raised for validation failures before the code reaches the sandbox."""


def _validate_source(source: str) -> None:
    if len(source) > _MAX_SOURCE_CHARS:
        raise CodeRunError("source_too_long")
    lowered = source.lower()
    for forbidden in _FORBIDDEN_IMPORTS:
        if forbidden in lowered:
            raise CodeRunError(f"forbidden_import:{forbidden}")


def _build_command(language: str, source_file: str) -> str:
    if language == "python":
        return f"python {source_file}"
    if language == "c":
        return f"gcc -std=c11 -O0 -o a.out {source_file} && ./a.out"
    if language == "cpp":
        return f"g++ -std=c++17 -O0 -o a.out {source_file} && ./a.out"
    raise CodeRunError(f"unsupported_language:{language}")


async def _run_once(
    sandbox: SandboxService,
    *,
    language: str,
    source_code: str,
    stdin: str,
    user_id: str,
) -> ExecResult:
    """Run the student's code once with the given stdin."""
    ext = {"python": "py", "c": "c", "cpp": "cpp"}.get(language, "py")
    source_file = f"solution.{ext}"
    limits = ResourceLimits(
        timeout_s=_MAX_TIMEOUT_S,
        memory_mb=256,
        cpu_seconds=10,
        max_output_chars=_MAX_OUTPUT_CHARS,
    )
    source_payload = base64.b64encode(source_code.encode("utf-8")).decode("ascii")
    stdin_payload = base64.b64encode(stdin.encode("utf-8")).decode("ascii")
    run_command = _build_command(language, source_file)

    # The sidecar root filesystem is read-only. Use an execution-specific tmp
    # directory and base64 payloads so source/stdin cannot break shell quoting.
    final_command = "\n".join(
        (
            'scratch="$(mktemp -d /tmp/deeptutor-k12.XXXXXX)"',
            "trap 'rm -rf \"$scratch\"' EXIT",
            'cd "$scratch"',
            (
                'python -c "import base64;'
                f"open('{source_file}','wb').write(base64.b64decode('{source_payload}'))\""
            ),
            (
                'python -c "import base64,sys;'
                f"sys.stdout.buffer.write(base64.b64decode('{stdin_payload}'))\" "
                f"| ({run_command})"
            ),
        )
    )
    request = ExecRequest(
        command=final_command,
        workdir="",
        env={},
        limits=limits,
    )
    return await sandbox.run(request, user_id=user_id)


def _check_output(actual: str, expected: str) -> bool:
    """Compare stdout with expected, normalising trailing whitespace."""
    return actual.strip() == expected.strip()


async def run_student_code(
    request: CodeRunRequest,
    *,
    user_id: str = "k12-student",
    sandbox: SandboxService | None = None,
) -> CodeRunResult:
    """Run student code against visible + hidden tests, return sanitised result."""
    task = get_coding_task(request.task_id)
    if task is None:
        raise CodeRunError("task_not_found")
    if task.course_id != request.course_id:
        raise CodeRunError("task_course_mismatch")
    if request.language not in task.allowed_languages:
        raise CodeRunError(f"language_not_allowed:{request.language}")

    _validate_source(request.source_code)

    svc = sandbox or get_sandbox_service()
    if not await svc.available():
        raise CodeRunError("sandbox_unavailable")

    visible_results: list[TestCaseResult] = []
    for test in task.visible_tests:
        result = await _run_once(
            svc,
            language=request.language,
            source_code=request.source_code,
            stdin=test.stdin,
            user_id=user_id,
        )
        passed = (
            result.exit_code == 0
            and not result.timed_out
            and _check_output(result.stdout, test.expected_stdout)
        )
        visible_results.append(
            TestCaseResult(
                name=test.name,
                passed=passed,
                stdout=result.stdout if not result.timed_out else "(timed out)",
                expected=test.expected_stdout,
            )
        )

    hidden_passed = 0
    for test in task.hidden_tests:
        result = await _run_once(
            svc,
            language=request.language,
            source_code=request.source_code,
            stdin=test.stdin,
            user_id=user_id,
        )
        passed = (
            result.exit_code == 0
            and not result.timed_out
            and _check_output(result.stdout, test.expected_stdout)
        )
        if passed:
            hidden_passed += 1

    # Run the student's raw code once (no test stdin) to capture stdout/stderr
    # for the "Run" button (as opposed to "Run tests").
    raw_result = await _run_once(
        svc,
        language=request.language,
        source_code=request.source_code,
        stdin=request.stdin,
        user_id=user_id,
    )

    return CodeRunResult(
        stdout=raw_result.stdout,
        stderr=raw_result.stderr,
        exit_code=raw_result.exit_code,
        timed_out=raw_result.timed_out,
        language=request.language,
        visible_results=visible_results,
        hidden_passed=hidden_passed,
        hidden_total=len(task.hidden_tests),
        all_visible_passed=all(r.passed for r in visible_results),
        all_hidden_passed=hidden_passed == len(task.hidden_tests),
    )


def get_hint(task: CodingTask, attempt_count: int) -> str:
    """Return a progressive hint. First attempt never reveals the full answer."""
    if attempt_count <= 0 or not task.hints:
        return "先检查报错信息和可见测试的输出，看看哪一步对不上。"
    index = min(attempt_count - 1, len(task.hints) - 1)
    return task.hints[index]


__all__ = [
    "CodeRunError",
    "get_hint",
    "run_student_code",
]
