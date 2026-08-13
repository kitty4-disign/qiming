from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.multi_user import identity, tool_access
from deeptutor.multi_user.context import reset_current_user, set_current_user
from deeptutor.multi_user.models import CurrentUser, UserScope


def _user(tmp_path: Path, *, user_id: str, role: str = "user") -> CurrentUser:
    return CurrentUser(
        id=user_id,
        username=user_id,
        role=role,  # type: ignore[arg-type]
        scope=UserScope(
            kind="admin" if role == "admin" else "user",
            user_id=user_id,
            root=tmp_path / user_id,
        ),
    )


def test_registered_non_admin_exec_is_denied_without_explicit_grant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity, "get_user_by_id", lambda uid: (uid, {"role": "user"}))
    monkeypatch.setattr(tool_access, "load_grant", lambda uid: {"exec_enabled": None})
    token = set_current_user(_user(tmp_path, user_id="u1"))
    try:
        assert tool_access.exec_override() is False
    finally:
        reset_current_user(token)


def test_registered_non_admin_exec_can_be_explicitly_granted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity, "get_user_by_id", lambda uid: (uid, {"role": "user"}))
    monkeypatch.setattr(tool_access, "load_grant", lambda uid: {"exec_enabled": True})
    token = set_current_user(_user(tmp_path, user_id="u1"))
    try:
        assert tool_access.exec_override() is True
    finally:
        reset_current_user(token)


def test_synthetic_partner_style_user_keeps_owner_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity, "get_user_by_id", lambda uid: None)
    token = set_current_user(_user(tmp_path, user_id="partner_demo"))
    try:
        assert tool_access.exec_override() is None
    finally:
        reset_current_user(token)


def test_unknown_non_partner_non_admin_exec_identity_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity, "get_user_by_id", lambda uid: None)
    token = set_current_user(_user(tmp_path, user_id="missing_user"))
    try:
        assert tool_access.exec_override() is False
    finally:
        reset_current_user(token)


def test_admin_exec_follows_deployment_policy(tmp_path: Path) -> None:
    token = set_current_user(_user(tmp_path, user_id="admin", role="admin"))
    try:
        assert tool_access.exec_override() is None
    finally:
        reset_current_user(token)
