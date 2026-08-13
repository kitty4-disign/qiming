"""Sandbox runner sidecar HTTP server (standard-library only).

This process runs *inside* the dedicated ``sandbox-runner`` container and is the
only place where untrusted shell commands are actually executed. The main app
never runs them itself; it submits work here over HTTP
(:class:`deeptutor.services.sandbox.backends.RunnerSidecarBackend`).

Design constraints:
  * No third-party deps (no FastAPI/Flask): the runner image must stay tiny and
    free of heavy frameworks. We use :mod:`http.server` directly.
  * Defence in depth: the container already drops privileges (non-root
    ``runner`` user, ``cap_drop: ALL``, ``no-new-privileges``, read-only rootfs
    — see ``Dockerfile.runner`` / ``docker-compose.yml``). On top of that we
    apply per-command resource limits via :func:`resource.setrlimit`.
  * ``POST /exec`` is fail-closed unless the caller presents the shared bearer
    token from ``DEEPTUTOR_SANDBOX_RUNNER_TOKEN``. ``GET /health`` remains
    unauthenticated so container orchestration can probe liveness.

Wire contract (must match ``RunnerSidecarBackend``):

  ``GET  /health`` -> 200, any body, means alive.
  ``POST /exec``   -> request/response JSON described by the dataclasses in
                      :mod:`deeptutor.services.sandbox.spec`.
"""

from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import sys
import traceback
from typing import Any, Mapping

try:
    import resource
except ImportError:  # pragma: no cover - Windows: resource is POSIX-only
    resource = None  # type: ignore[assignment]

DEFAULT_PORT = 8900
RUNNER_TOKEN_ENV = "DEEPTUTOR_SANDBOX_RUNNER_TOKEN"
_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_DEFAULT_TIMEOUT_S = 30
_DEFAULT_MEMORY_MB = 512
_DEFAULT_CPU_SECONDS = 30
_DEFAULT_MAX_OUTPUT_CHARS = 10_000
_RLIMIT_NOFILE = 4096
_POSIX = os.name == "posix"


def _truncate_head_tail(text: str, max_chars: int) -> str:
    """Cap *text* to *max_chars*, keeping the head and tail."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    half = max_chars // 2
    dropped = len(text) - max_chars
    return text[:half] + f"\n\n... ({dropped:,} chars truncated) ...\n\n" + text[-half:]


def _build_preexec_fn(memory_mb: int, cpu_seconds: int):
    """Return a ``preexec_fn`` that applies rlimits in the forked child."""
    if not _POSIX:
        return None

    def _apply() -> None:
        if memory_mb > 0:
            mem_bytes = memory_mb * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except (ValueError, OSError):
                pass
        if cpu_seconds > 0:
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            except (ValueError, OSError):
                pass
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (_RLIMIT_NOFILE, _RLIMIT_NOFILE))
        except (ValueError, OSError):
            pass

    return _apply


_ALLOWED_WORKDIR_ROOTS = [
    root
    for root in os.environ.get(
        "DEEPTUTOR_RUNNER_ALLOWED_WORKDIRS",
        "/app/data/user/workspace:/app/data/users",
    ).split(":")
    if root
]


def _configured_token() -> str:
    return os.environ.get(RUNNER_TOKEN_ENV, "").strip()


def _request_authorized(headers: Mapping[str, str]) -> bool:
    """Constant-time bearer-token check; missing server token fails closed."""
    expected = _configured_token()
    if not expected:
        return False
    authorization = str(headers.get("Authorization", "") or "")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return False
    provided = authorization[len(prefix) :].strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


def _workdir_violation(workdir: str) -> str:
    """Return a rejection reason, or '' when *workdir* is acceptable."""
    resolved = os.path.realpath(workdir)
    for root in _ALLOWED_WORKDIR_ROOTS:
        root_real = os.path.realpath(root)
        if resolved == root_real or resolved.startswith(root_real + os.sep):
            return ""
    return (
        f"workdir {workdir!r} is outside the shared workspace roots "
        f"({':'.join(_ALLOWED_WORKDIR_ROOTS)}); refusing to execute"
    )


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one command described by *payload* and return the response dict.

    Authentication is an HTTP-boundary concern and is enforced by ``_Handler``;
    keeping this pure function separate makes request-shape/resource tests fast.
    """
    command = payload.get("command")
    if not isinstance(command, str) or not command:
        return _error_result("missing or empty 'command'")

    workdir = payload.get("workdir") or None
    if workdir is not None and not isinstance(workdir, str):
        return _error_result("'workdir' must be a string or null")
    if workdir is not None:
        reason = _workdir_violation(workdir)
        if reason:
            return _error_result(reason)

    raw_env = payload.get("env") or {}
    if not isinstance(raw_env, dict):
        return _error_result("'env' must be an object")
    env: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
    for key, value in raw_env.items():
        env[str(key)] = str(value)

    mounts = payload.get("mounts") or []
    if not isinstance(mounts, list):
        return _error_result("'mounts' must be a list")

    limits = payload.get("limits") or {}
    if not isinstance(limits, dict):
        return _error_result("'limits' must be an object")
    timeout_s = _int(limits.get("timeout_s"), _DEFAULT_TIMEOUT_S)
    memory_mb = _int(limits.get("memory_mb"), _DEFAULT_MEMORY_MB)
    cpu_seconds = _int(limits.get("cpu_seconds"), _DEFAULT_CPU_SECONDS)
    max_output_chars = _int(limits.get("max_output_chars"), _DEFAULT_MAX_OUTPUT_CHARS)

    if not _POSIX or resource is None:
        return _error_result(
            "sandbox runner requires a POSIX platform with resource limits "
            "(unsupported on Windows)"
        )

    preexec_fn = _build_preexec_fn(memory_mb, cpu_seconds)

    try:
        completed = subprocess.run(  # noqa: S602 - shell=True is the contract
            command,
            shell=True,  # nosec B602 — command executes inside hardened runner container
            cwd=workdir,
            env=env,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            preexec_fn=preexec_fn,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode(exc.stdout)
        stderr = _decode(exc.stderr)
        return {
            "stdout": _truncate_head_tail(stdout, max_output_chars),
            "stderr": _truncate_head_tail(stderr, max_output_chars),
            "exit_code": 124,
            "timed_out": True,
            "error": "",
        }
    except (OSError, ValueError) as exc:
        # Keep potentially sensitive filesystem details in container logs only.
        traceback.print_exc()
        return _error_result(f"runner spawn failed: {type(exc).__name__}")

    return {
        "stdout": _truncate_head_tail(completed.stdout or "", max_output_chars),
        "stderr": _truncate_head_tail(completed.stderr or "", max_output_chars),
        "exit_code": completed.returncode,
        "timed_out": False,
        "error": "",
    }


def _decode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _int(value: Any, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default


def _error_result(message: str) -> dict[str, Any]:
    return {
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "error": message,
    }


class _Handler(BaseHTTPRequestHandler):
    """Minimal request router for ``GET /health`` and authenticated ``POST /exec``."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stdout.write("runner: " + (format % args) + "\n")

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path.rstrip("/") == "/health" or self.path == "/":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json(404, _error_result("not found"))

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if self.path.rstrip("/") != "/exec":
            self._send_json(404, _error_result("not found"))
            return
        if not _request_authorized(self.headers):
            self._send_json(401, _error_result("unauthorized"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, _error_result("invalid Content-Length"))
            return
        if length > _MAX_REQUEST_BYTES:
            self._send_json(413, _error_result("request body too large"))
            return
        try:
            raw = self.rfile.read(length) if length > 0 else b""
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, _error_result("invalid JSON"))
            return

        try:
            result = execute(payload)
        except Exception:  # noqa: BLE001 - last-resort guard
            traceback.print_exc()
            result = _error_result("runner internal error")
        self._send_json(200, result)


def main() -> None:
    """Start the threaded HTTP server, binding inside the runner container."""
    if not _POSIX or resource is None:
        sys.stderr.write(
            "sandbox runner requires POSIX resource limits; refusing to serve on Windows\n"
        )
        sys.exit(2)
    if not _configured_token():
        sys.stderr.write(
            f"runner: {RUNNER_TOKEN_ENV} is not set; /exec will reject all requests\n"
        )
    try:
        port = int(os.environ.get("RUNNER_PORT", "") or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    sys.stdout.write(f"runner: listening on 0.0.0.0:{port}\n")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
