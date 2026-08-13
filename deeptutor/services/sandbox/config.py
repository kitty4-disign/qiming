"""
Sandbox configuration and backend selection.

The active backend is chosen from environment so it tracks the deployment
shape without per-user config:

* ``DEEPTUTOR_SANDBOX_RUNNER_URL`` set ⇒ runner sidecar (Docker deployment);
* else on Linux with a functional ``bwrap`` ⇒ bwrap (bare-metal);
* else restricted subprocess is available only when BOTH
  ``DEEPTUTOR_SANDBOX_ALLOW_SUBPROCESS=1`` and
  ``DEEPTUTOR_SANDBOX_ACK_UNSAFE_HOST_SUBPROCESS=1`` are set;
* else ⇒ no sandbox (exec disabled).

The second subprocess flag is intentionally not emitted by runtime settings.
It is an operator acknowledgement that APPLICATION isolation executes a shell
on the host and is not a security boundary. This prevents legacy/default
``sandbox_allow_subprocess=true`` settings from silently enabling host shell.

The runner sidecar's ``/exec`` endpoint additionally requires the shared
``DEEPTUTOR_SANDBOX_RUNNER_TOKEN`` bearer token. A configured runner URL with
no token therefore fails closed at execution time instead of exposing an
unauthenticated container shell.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from deeptutor.services.sandbox.backends import (
    BwrapBackend,
    RestrictedSubprocessBackend,
    RunnerSidecarBackend,
    SandboxBackend,
)
from deeptutor.services.sandbox.spec import ResourceLimits

RUNNER_URL_ENV = "DEEPTUTOR_SANDBOX_RUNNER_URL"
RUNNER_TOKEN_ENV = "DEEPTUTOR_SANDBOX_RUNNER_TOKEN"
ALLOW_SUBPROCESS_ENV = "DEEPTUTOR_SANDBOX_ALLOW_SUBPROCESS"
ACK_UNSAFE_SUBPROCESS_ENV = "DEEPTUTOR_SANDBOX_ACK_UNSAFE_HOST_SUBPROCESS"

MAX_CONCURRENT_ENV = "DEEPTUTOR_SANDBOX_MAX_CONCURRENT"
MAX_PER_MINUTE_ENV = "DEEPTUTOR_SANDBOX_MAX_PER_MINUTE"


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SandboxSettings:
    runner_url: str = ""
    runner_token: str = ""
    allow_subprocess: bool = False
    default_limits: ResourceLimits = ResourceLimits()
    max_concurrent_per_user: int = 2
    max_runs_per_minute_per_user: int = 20

    @classmethod
    def from_env(cls) -> "SandboxSettings":
        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, "") or default)
            except ValueError:
                return default

        requested_subprocess = _truthy(os.environ.get(ALLOW_SUBPROCESS_ENV, ""))
        acknowledged_unsafe = _truthy(os.environ.get(ACK_UNSAFE_SUBPROCESS_ENV, ""))
        return cls(
            runner_url=os.environ.get(RUNNER_URL_ENV, "").strip(),
            runner_token=os.environ.get(RUNNER_TOKEN_ENV, "").strip(),
            allow_subprocess=requested_subprocess and acknowledged_unsafe,
            max_concurrent_per_user=_int(MAX_CONCURRENT_ENV, 2),
            max_runs_per_minute_per_user=_int(MAX_PER_MINUTE_ENV, 20),
        )


def build_backend(settings: SandboxSettings) -> SandboxBackend | None:
    """Pick the backend implied by *settings*; ``None`` when none is usable.

    Note: returns the candidate by configuration shape. Liveness (e.g. can
    bwrap actually create namespaces here) is confirmed lazily via the
    backend's ``health()`` — see :mod:`deeptutor.services.sandbox.service`.
    """
    import sys

    if settings.runner_url:
        return RunnerSidecarBackend(settings.runner_url, token=settings.runner_token)
    if sys.platform.startswith("linux"):
        import shutil

        if shutil.which("bwrap"):
            return BwrapBackend()
    if settings.allow_subprocess:
        return RestrictedSubprocessBackend()
    return None


__all__ = [
    "ACK_UNSAFE_SUBPROCESS_ENV",
    "ALLOW_SUBPROCESS_ENV",
    "RUNNER_TOKEN_ENV",
    "RUNNER_URL_ENV",
    "SandboxSettings",
    "build_backend",
]
