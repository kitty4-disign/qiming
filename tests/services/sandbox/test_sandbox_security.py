from __future__ import annotations

import os
import sys

import pytest

from deeptutor.services.sandbox.backends import RestrictedSubprocessBackend, RunnerSidecarBackend
from deeptutor.services.sandbox.config import SandboxSettings
from deeptutor.services.sandbox.spec import ExecRequest


def test_sandbox_settings_load_runner_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_SANDBOX_RUNNER_URL", "http://runner:8900")
    monkeypatch.setenv("DEEPTUTOR_SANDBOX_RUNNER_TOKEN", "secret-token")

    settings = SandboxSettings.from_env()

    assert settings.runner_url == "http://runner:8900"
    assert settings.runner_token == "secret-token"


def test_host_subprocess_requires_separate_unsafe_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_SANDBOX_ALLOW_SUBPROCESS", "1")
    monkeypatch.delenv("DEEPTUTOR_SANDBOX_ACK_UNSAFE_HOST_SUBPROCESS", raising=False)
    assert SandboxSettings.from_env().allow_subprocess is False

    monkeypatch.setenv("DEEPTUTOR_SANDBOX_ACK_UNSAFE_HOST_SUBPROCESS", "1")
    assert SandboxSettings.from_env().allow_subprocess is True


@pytest.mark.asyncio
async def test_runner_backend_without_token_fails_closed_before_http() -> None:
    backend = RunnerSidecarBackend("http://runner:8900")

    result = await backend.exec(ExecRequest(command="echo should-not-run"))

    assert not result.ok
    assert "token" in result.error.lower()


def test_runner_http_auth_fails_closed_and_accepts_matching_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.sandbox.runner import server

    monkeypatch.delenv("DEEPTUTOR_SANDBOX_RUNNER_TOKEN", raising=False)
    assert server._request_authorized({"Authorization": "Bearer anything"}) is False

    monkeypatch.setenv("DEEPTUTOR_SANDBOX_RUNNER_TOKEN", "expected")
    assert server._request_authorized({}) is False
    assert server._request_authorized({"Authorization": "Bearer wrong"}) is False
    assert server._request_authorized({"Authorization": "Bearer expected"}) is True


@pytest.mark.asyncio
async def test_restricted_subprocess_does_not_accept_path_override() -> None:
    backend = RestrictedSubprocessBackend()
    command = f'"{sys.executable}" -c "import os; print(os.environ.get(\'PATH\', \'\'))"'

    result = await backend.exec(
        ExecRequest(command=command, env={"PATH": "ATTACKER_CONTROLLED_PATH"})
    )

    assert result.ok
    assert "ATTACKER_CONTROLLED_PATH" not in result.stdout
    if "PATH" in os.environ:
        assert os.environ["PATH"] in result.stdout
