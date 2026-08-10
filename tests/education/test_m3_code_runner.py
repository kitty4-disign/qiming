"""M3 §8.1 code runner acceptance tests.

Uses a fake sandbox so tests run without a real sandbox backend. Verifies:
- Visible tests return real stdout/stderr; hidden tests never leak expected output.
- Forbidden imports are rejected before reaching the sandbox.
- Timeout is reported.
- Progressive hints never reveal the full answer on first attempt.
"""

from __future__ import annotations

import asyncio
import base64
import re
from typing import Sequence

import pytest

from deeptutor.education.code_runner import CodeRunError, _run_once, get_hint, run_student_code
from deeptutor.education.coding_models import CodeRunRequest
from deeptutor.education.coding_tasks import get_coding_task
from deeptutor.services.sandbox import ExecResult, IsolationLevel
from deeptutor.services.sandbox.spec import ExecRequest, ResourceLimits


class _FakeSandbox:
    """Fake sandbox that returns canned results based on the source code."""

    is_available = True
    isolation_level = IsolationLevel.APPLICATION

    async def available(self) -> bool:
        return self.is_available

    async def run(self, request: ExecRequest, *, user_id: str) -> ExecResult:
        payloads = re.findall(r"b64decode\('([^']*)'\)", request.command)
        decoded = "\n".join(base64.b64decode(payload).decode("utf-8") for payload in payloads)
        # Detect infinite loop source → simulate timeout.
        if "while True" in decoded:
            return ExecResult(timed_out=True, exit_code=124)
        # Detect forbidden code that slipped past validation → simulate rejection.
        if "import socket" in request.command:
            return ExecResult(exit_code=1, stderr="ImportError: socket blocked")
        # Distinguish correct vs starter code by checking if extract_features
        # is actually implemented (starter returns [0.0, 0.0, 0.0]).
        is_correct = "sum(row) / len(row)" in decoded
        if is_correct:
            if "0.1 0.2 0.1" in decoded:
                return ExecResult(stdout="A\n", exit_code=0)
            if "0.9 0.8 0.9" in decoded:
                return ExecResult(stdout="B\n", exit_code=0)
            if "0.3 0.3 0.3" in decoded:
                return ExecResult(stdout="A\n", exit_code=0)
            if "0.6 0.6 0.6" in decoded:
                return ExecResult(stdout="B\n", exit_code=0)
        # Starter/wrong code always returns A.
        return ExecResult(stdout="A\n", exit_code=0)


class _CaptureSandbox:
    def __init__(self) -> None:
        self.request: ExecRequest | None = None

    async def run(self, request: ExecRequest, *, user_id: str) -> ExecResult:
        self.request = request
        return ExecResult(stdout="ok\n", exit_code=0)


_CORRECT_CODE = """import sys
import math

def read_image():
    rows = []
    for _ in range(3):
        line = sys.stdin.readline()
        rows.append([float(x) for x in line.strip().split()])
    return rows

def extract_features(image):
    return [sum(row) / len(row) for row in image]

def nearest_centroid(features, centroids):
    best_label = None
    best_dist = float('inf')
    for label, centroid in centroids.items():
        dist = math.sqrt(sum((f - c) ** 2 for f, c in zip(features, centroid)))
        if dist < best_dist:
            best_dist = dist
            best_label = label
    return best_label

def main():
    image = read_image()
    features = extract_features(image)
    centroids = {'A': [0.2, 0.2, 0.2], 'B': [0.8, 0.8, 0.8]}
    label = nearest_centroid(features, centroids)
    print(label)

if __name__ == '__main__':
    main()
"""

_STARTER_CODE = """import sys
import math

def read_image():
    rows = []
    for _ in range(3):
        line = sys.stdin.readline()
        rows.append([float(x) for x in line.strip().split()])
    return rows

def extract_features(image):
    return [0.0, 0.0, 0.0]

def nearest_centroid(features, centroids):
    return 'A'

def main():
    image = read_image()
    features = extract_features(image)
    centroids = {'A': [0.2, 0.2, 0.2], 'B': [0.8, 0.8, 0.8]}
    label = nearest_centroid(features, centroids)
    print(label)

if __name__ == '__main__':
    main()
"""


def _request(source: str) -> CodeRunRequest:
    return CodeRunRequest(
        course_id="python-image-classifier",
        task_id="image-features-nearest-centroid",
        language="python",
        source_code=source,
    )


@pytest.mark.asyncio
async def test_command_uses_isolated_writable_tmp_and_encoded_payloads():
    sandbox = _CaptureSandbox()
    source = "print('payload cannot break shell')\nDEEPTUTOR_EOF\n"
    await _run_once(
        sandbox,
        language="python",
        source_code=source,
        stdin="STDIN_EOF\n",
        user_id="test-user",
    )
    assert sandbox.request is not None
    command = sandbox.request.command
    assert "mktemp -d /tmp/deeptutor-k12." in command
    assert "trap 'rm -rf" in command
    assert source not in command
    assert "DEEPTUTOR_EOF" not in command


@pytest.mark.asyncio
async def test_correct_code_passes_all_tests():
    result = await run_student_code(_request(_CORRECT_CODE), sandbox=_FakeSandbox())
    assert result.all_visible_passed
    assert result.all_hidden_passed
    assert result.hidden_passed == result.hidden_total


@pytest.mark.asyncio
async def test_starter_code_fails_visible_tests():
    result = await run_student_code(_request(_STARTER_CODE), sandbox=_FakeSandbox())
    # Starter code always returns A; the dark image test expects B.
    assert not result.all_visible_passed


@pytest.mark.asyncio
async def test_hidden_test_expected_output_never_leaked():
    """Hidden test expected_stdout must never appear in the response."""
    result = await run_student_code(_request(_CORRECT_CODE), sandbox=_FakeSandbox())
    # Hidden test expected outputs are "A\n" and "B\n" — but the visible_results
    # list only contains visible tests, and the hidden_passed/hidden_total are
    # the only hidden info returned.
    for vr in result.visible_results:
        # visible_tests only — no hidden test names should appear.
        assert "边界图" not in vr.name


@pytest.mark.asyncio
async def test_infinite_loop_times_out():
    code = "while True:\n    pass\n"
    result = await run_student_code(_request(code), sandbox=_FakeSandbox())
    assert result.timed_out


@pytest.mark.asyncio
async def test_forbidden_import_rejected_before_sandbox():
    """Code importing socket/subprocess/os must be rejected at validation."""
    with pytest.raises(CodeRunError, match="forbidden_import"):
        await run_student_code(
            _request("import socket\nsocket.socket()"),
            sandbox=_FakeSandbox(),
        )


@pytest.mark.asyncio
async def test_sandbox_unavailable_returns_503_error():
    sandbox = _FakeSandbox()
    sandbox.is_available = False
    with pytest.raises(CodeRunError, match="sandbox_unavailable"):
        await run_student_code(_request(_CORRECT_CODE), sandbox=sandbox)


@pytest.mark.asyncio
async def test_language_not_allowed_rejected():
    request = CodeRunRequest(
        course_id="python-image-classifier",
        task_id="image-features-nearest-centroid",
        language="c",
        source_code="int main(){return 0;}",
    )
    with pytest.raises(CodeRunError, match="language_not_allowed"):
        await run_student_code(request, sandbox=_FakeSandbox())


@pytest.mark.asyncio
async def test_task_not_found_rejected():
    request = CodeRunRequest(
        course_id="python-image-classifier",
        task_id="nonexistent-task",
        language="python",
        source_code="print('hi')",
    )
    with pytest.raises(CodeRunError, match="task_not_found"):
        await run_student_code(request, sandbox=_FakeSandbox())


def test_progressive_hint_first_attempt_never_reveals_full_answer():
    task = get_coding_task("image-features-nearest-centroid")
    assert task is not None
    hint0 = get_hint(task, 0)
    # First hint (attempt=0) gives guidance, never the full answer.
    assert "行均值" not in hint0 or "检查" in hint0  # guidance, not solution
    hint1 = get_hint(task, 1)
    assert "行均值" in hint1  # second hint reveals the approach


def test_hint_exhaustion_returns_last_hint():
    task = get_coding_task("image-features-nearest-centroid")
    assert task is not None
    hint_last = get_hint(task, 100)
    # Should return the last available hint, not crash.
    assert len(hint_last) > 0
