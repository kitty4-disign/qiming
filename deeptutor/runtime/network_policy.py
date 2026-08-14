"""Network exposure guardrails shared by DeepTutor launch paths."""

from __future__ import annotations

import ipaddress
import os
from typing import Mapping

UNSAFE_REMOTE_ACK_ENV = "DEEPTUTOR_ACK_UNAUTHENTICATED_REMOTE"
_TRUTHY = {"1", "true", "yes", "on"}


def is_loopback_host(host: str) -> bool:
    """Return whether ``host`` is an explicit loopback-only bind target."""
    value = str(host or "").strip().lower()
    if not value:
        return False
    if value == "localhost":
        return True
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def unauthenticated_remote_acknowledged(env: Mapping[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return str(values.get(UNSAFE_REMOTE_ACK_ENV, "")).strip().lower() in _TRUTHY


def require_safe_bind(
    host: str,
    *,
    auth_enabled: bool,
    env: Mapping[str, str] | None = None,
) -> str:
    """Reject remotely reachable unauthenticated binds unless explicitly acknowledged.

    Auth-disabled local development remains zero-config on loopback. A deployer
    that intentionally exposes an unauthenticated instance must opt into that
    risk with ``DEEPTUTOR_ACK_UNAUTHENTICATED_REMOTE=1``; merely changing the
    bind host is not enough to make the API reachable from another machine.
    """
    resolved = str(host or "").strip()
    if not resolved:
        raise RuntimeError("DeepTutor bind host cannot be empty")
    if auth_enabled or is_loopback_host(resolved):
        return resolved
    if unauthenticated_remote_acknowledged(env):
        return resolved
    raise RuntimeError(
        "Refusing to bind DeepTutor to a non-loopback host while authentication is disabled. "
        "Enable auth before remote/LAN exposure. If this unauthenticated exposure is "
        "intentional, set DEEPTUTOR_ACK_UNAUTHENTICATED_REMOTE=1 explicitly."
    )


__all__ = [
    "UNSAFE_REMOTE_ACK_ENV",
    "is_loopback_host",
    "require_safe_bind",
    "unauthenticated_remote_acknowledged",
]
