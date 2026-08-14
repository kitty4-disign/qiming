from __future__ import annotations

import pytest

from deeptutor.runtime.network_policy import require_safe_bind


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.42", "::1", "[::1]", "localhost"])
def test_auth_disabled_allows_loopback(host: str) -> None:
    assert require_safe_bind(host, auth_enabled=False, env={}) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "api.internal"])
def test_auth_disabled_rejects_remote_bind_without_explicit_ack(host: str) -> None:
    with pytest.raises(RuntimeError, match="authentication is disabled"):
        require_safe_bind(host, auth_enabled=False, env={})


def test_auth_enabled_allows_remote_bind() -> None:
    assert require_safe_bind("0.0.0.0", auth_enabled=True, env={}) == "0.0.0.0"


def test_explicit_ack_allows_intentional_unauthenticated_remote_bind() -> None:
    env = {"DEEPTUTOR_ACK_UNAUTHENTICATED_REMOTE": "1"}
    assert require_safe_bind("0.0.0.0", auth_enabled=False, env=env) == "0.0.0.0"
