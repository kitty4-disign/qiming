from __future__ import annotations

from typing import Any

import pytest

from deeptutor.api.routers import unified_ws


class _Store:
    def __init__(self) -> None:
        self.sessions = {"mine": {"id": "mine"}}
        self.turns = {"turn-mine": {"id": "turn-mine", "session_id": "mine"}}

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.sessions.get(session_id)

    async def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        return self.turns.get(turn_id)


@pytest.mark.asyncio
async def test_current_user_session_lookup_fails_closed_for_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeptutor.services.session as session_module

    store = _Store()
    monkeypatch.setattr(session_module, "get_session_store", lambda: store)

    assert await unified_ws._current_user_has_session("mine") is True
    assert await unified_ws._current_user_has_session("someone-elses-session") is False
    assert await unified_ws._current_user_has_session("") is False


@pytest.mark.asyncio
async def test_current_user_turn_lookup_fails_closed_for_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeptutor.services.session as session_module

    store = _Store()
    monkeypatch.setattr(session_module, "get_session_store", lambda: store)

    assert await unified_ws._current_user_has_turn("turn-mine") is True
    assert await unified_ws._current_user_has_turn("turn-someone-else") is False
    assert await unified_ws._current_user_has_turn("") is False


def test_dead_user_input_route_is_not_advertised() -> None:
    assert "``user_input``" not in (unified_ws.__doc__ or "")
