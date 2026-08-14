from __future__ import annotations

import pytest

from deeptutor.api import main as api_main


def test_api_startup_rejects_remote_exposure_when_auth_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main, "load_auth_settings", lambda: {"enabled": False})
    monkeypatch.setenv("DEEPTUTOR_EXPOSURE_HOST", "0.0.0.0")
    monkeypatch.delenv("DEEPTUTOR_API_HOST", raising=False)
    monkeypatch.delenv("DEEPTUTOR_ACK_UNAUTHENTICATED_REMOTE", raising=False)

    with pytest.raises(RuntimeError, match="authentication is disabled"):
        api_main.validate_network_exposure()


def test_api_startup_allows_remote_exposure_when_auth_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main, "load_auth_settings", lambda: {"enabled": True})
    monkeypatch.setenv("DEEPTUTOR_EXPOSURE_HOST", "0.0.0.0")
    monkeypatch.delenv("DEEPTUTOR_API_HOST", raising=False)

    api_main.validate_network_exposure()


def test_api_startup_allows_loopback_without_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main, "load_auth_settings", lambda: {"enabled": False})
    monkeypatch.setenv("DEEPTUTOR_API_HOST", "127.0.0.1")
    monkeypatch.delenv("DEEPTUTOR_EXPOSURE_HOST", raising=False)

    api_main.validate_network_exposure()
